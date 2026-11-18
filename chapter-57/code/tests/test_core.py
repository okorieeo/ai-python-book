import io
import json
import os
import threading
import unittest
import zipfile
from datetime import datetime, timezone

import docx
from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from docuask_core import evals
from docuask_core.chunking import Page, chunk_pages, split_sentences
from docuask_core.citations import NO_ANSWER_TEXT, StreamAssembler, parse_response
from docuask_core.embeddings import HashingEmbedder, TransientEmbeddingError, embed_in_batches, with_retries
from docuask_core.extract import ExtractionError, NoTextError, extract_pages, sniff_type
from docuask_core.limits import PLANS, InMemoryLedger, LimitExceeded, billable_pages, check_upload, consume, next_reset, period_start
from docuask_core.prompting import RetrievedChunk, build_messages, build_search_results, chunk_to_blocks
from docuask_core.retrieval import (cosine, drop_near_duplicates, fit_to_budget, keyword_rank, limit_per_group,
                                    rrf, should_answer, vector_rank)
from docuask_core.text import estimate_tokens, normalize_text

HERE = os.path.dirname(__file__)
CORPUS = os.path.join(HERE, "fixtures", "corpus")


def make_pdf(pages):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for text in pages:
        y = 800
        for line in text.split("\n"):
            c.drawString(50, y, line)
            y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


class TextTests(unittest.TestCase):
    def test_normalize_fixes_extraction_artifacts(self):
        raw = "The infor-\nmation is\nin one paragraph.\n\n\nSecond\x00 paragraph\u00a0here.  \ufb01nance"
        self.assertEqual(normalize_text(raw), "The information is in one paragraph.\n\nSecond paragraph here. finance")

    def test_token_estimate(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd" * 10), 10)


class ChunkingTests(unittest.TestCase):
    TEXT = " ".join(f"Sentence number {i} talks about topic {i % 7} in some detail." for i in range(60))

    def test_chunks_respect_size_limits(self):
        chunks = chunk_pages([Page(1, self.TEXT)], target_tokens=60, max_tokens=90, min_tokens=10)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(c.tokens <= 90 for c in chunks))
        self.assertEqual([c.index for c in chunks], list(range(len(chunks))))

    def test_chunks_never_cross_pages(self):
        pages = [Page(1, self.TEXT), Page(2, self.TEXT), Page(3, "A short final page. It has two sentences.")]
        chunks = chunk_pages(pages, target_tokens=60, max_tokens=90, min_tokens=10)
        self.assertTrue(all(c.page_start == c.page_end for c in chunks))
        self.assertEqual({c.page_start for c in chunks}, {1, 2, 3})

    def test_overlap_repeats_the_last_sentence(self):
        chunks = chunk_pages([Page(1, self.TEXT)], target_tokens=60, max_tokens=90, min_tokens=10, overlap_sentences=1)
        first_last = split_sentences(chunks[0].text)[-1]
        self.assertTrue(chunks[1].text.startswith(first_last))

    def test_no_overlap_option(self):
        chunks = chunk_pages([Page(1, self.TEXT)], target_tokens=60, max_tokens=90, min_tokens=10, overlap_sentences=0)
        joined = " ".join(c.text for c in chunks)
        self.assertEqual(joined.count("Sentence number 0 "), 1)

    def test_every_sentence_is_covered(self):
        chunks = chunk_pages([Page(1, self.TEXT)], target_tokens=60, max_tokens=90, min_tokens=10)
        joined = " ".join(c.text for c in chunks)
        for i in range(60):
            self.assertIn(f"Sentence number {i} ", joined)

    def test_a_giant_unpunctuated_run_is_hard_split(self):
        chunks = chunk_pages([Page(1, "word " * 2000)], target_tokens=60, max_tokens=90, min_tokens=10)
        self.assertTrue(all(c.tokens <= 90 for c in chunks))
        self.assertGreater(len(chunks), 10)

    def test_empty_pages_make_no_chunks_and_bad_parameters_raise(self):
        self.assertEqual(chunk_pages([Page(1, "   "), Page(2, "")]), [])
        with self.assertRaises(ValueError):
            chunk_pages([Page(1, "x")], target_tokens=10, max_tokens=5)

    def test_hash_is_stable_and_differs_by_text(self):
        a = chunk_pages([Page(1, "One sentence here. Another sentence there.")])
        b = chunk_pages([Page(1, "One sentence here. Another sentence there.")])
        c = chunk_pages([Page(1, "Different text entirely, with new words.")])
        self.assertEqual(a[0].sha256, b[0].sha256)
        self.assertNotEqual(a[0].sha256, c[0].sha256)


class ExtractTests(unittest.TestCase):
    def test_pdf_pages_and_numbers(self):
        data = make_pdf(["Alpha page one has enough text to count.", "Beta page two also has enough text here."])
        pages = extract_pages(data, "report.pdf")
        self.assertEqual([p.number for p in pages], [1, 2])
        self.assertIn("Alpha", pages[0].text)
        self.assertIn("Beta", pages[1].text)

    def test_scanned_pdf_is_refused_with_a_helpful_message(self):
        w = PdfWriter()
        w.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        w.write(buf)
        with self.assertRaises(NoTextError) as cm:
            extract_pages(buf.getvalue(), "scan.pdf")
        self.assertIn("OCR", str(cm.exception))

    def test_encrypted_pdf_is_refused(self):
        w = PdfWriter()
        w.add_blank_page(width=200, height=200)
        w.encrypt("secret")
        buf = io.BytesIO()
        w.write(buf)
        with self.assertRaises(ExtractionError) as cm:
            extract_pages(buf.getvalue(), "locked.pdf")
        self.assertIn("password", str(cm.exception))

    def test_page_limit(self):
        data = make_pdf(["A line with enough text on page %d." % i for i in range(5)])
        with self.assertRaises(ExtractionError):
            extract_pages(data, "long.pdf", max_pages=3)

    def test_docx_text_and_tables(self):
        d = docx.Document()
        d.add_paragraph("Policy overview paragraph.")
        t = d.add_table(rows=1, cols=2)
        t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Limit", "500 USD"
        buf = io.BytesIO()
        d.save(buf)
        pages = extract_pages(buf.getvalue(), "policy.docx")
        self.assertEqual(len(pages), 1)
        self.assertIsNone(pages[0].number)
        self.assertIn("Limit | 500 USD", pages[0].text)

    def test_zip_bomb_is_rejected_before_parsing(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("word/document.xml", b"0" * 5_000_000)
        self.assertLess(len(buf.getvalue()), 50_000)
        with self.assertRaises(ExtractionError) as cm:
            extract_pages(buf.getvalue(), "bomb.docx", max_uncompressed=1_000_000)
        self.assertIn("unreasonable size", str(cm.exception))

    def test_text_file_with_form_feeds_gets_page_numbers(self):
        pages = extract_pages("Page one text.\fPage two text.".encode(), "notes.txt")
        self.assertEqual([p.number for p in pages], [1, 2])
        self.assertIsNone(extract_pages(b"Just one block of text.", "notes.md")[0].number)

    def test_latin1_text_file(self):
        self.assertIn("caf\u00e9", extract_pages("caf\u00e9 au lait".encode("cp1252"), "menu.txt")[0].text)

    def test_the_file_name_is_not_trusted(self):
        with self.assertRaises(ExtractionError):
            extract_pages(b"MZ\x90\x00 this is a Windows program", "invoice.pdf")
        with self.assertRaises(ExtractionError):
            extract_pages(make_pdf(["Real PDF content for the test."]), "renamed.docx")
        with self.assertRaises(ExtractionError):
            sniff_type(b"x" * 10, "archive.zip")

    def test_damaged_pdf_gives_a_friendly_error(self):
        with self.assertRaises(ExtractionError):
            extract_pages(b"%PDF-1.7\nthis is not really a pdf", "broken.pdf")


class EmbeddingTests(unittest.TestCase):
    def test_hashing_embedder_is_deterministic_unit_length_and_lexical(self):
        e = HashingEmbedder(256)
        v1, v2 = e.embed_query("annual leave days"), e.embed_query("annual leave days")
        self.assertEqual(v1, v2)
        self.assertAlmostEqual(sum(x * x for x in v1), 1.0, places=6)
        near = cosine(v1, e.embed_documents(["You get 25 days of annual leave."])[0])
        far = cosine(v1, e.embed_documents(["The pump is blocked by scale."])[0])
        self.assertGreater(near, far + 0.2)

    def test_batching_by_count_and_size_keeps_order(self):
        calls = []

        class Spy(HashingEmbedder):
            def embed_documents(self, texts):
                calls.append(len(texts))
                return super().embed_documents(texts)

        texts = [f"document {i} about thing {i}" for i in range(10)]
        out = embed_in_batches(Spy(64), texts, batch_size=4)
        self.assertEqual(calls, [4, 4, 2])
        self.assertEqual(out, HashingEmbedder(64).embed_documents(texts))
        calls.clear()
        embed_in_batches(Spy(64), ["x" * 60] * 5, batch_size=100, max_chars_per_batch=130)
        self.assertEqual(calls, [2, 2, 1])

    def test_retry_with_backoff_then_success(self):
        delays, state = [], {"n": 0}

        def flaky():
            state["n"] += 1
            if state["n"] < 4:
                raise TransientEmbeddingError("429")
            return "ok"

        self.assertEqual(with_retries(flaky, attempts=5, base_delay=1, sleep=delays.append), "ok")
        self.assertEqual(delays, [1, 2, 4])

    def test_retry_gives_up_and_does_not_retry_other_errors(self):
        def always():
            raise TransientEmbeddingError("503")
        with self.assertRaises(TransientEmbeddingError):
            with_retries(always, attempts=3, sleep=lambda s: None)
        calls = []

        def bad():
            calls.append(1)
            raise ValueError("bad input")
        with self.assertRaises(ValueError):
            with_retries(bad, attempts=5, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)

    def test_provider_returning_wrong_count_is_detected(self):
        class Broken(HashingEmbedder):
            def embed_documents(self, texts):
                return super().embed_documents(texts)[:-1]
        with self.assertRaises(RuntimeError):
            embed_in_batches(Broken(8), ["a b", "c d"])


class RetrievalTests(unittest.TestCase):
    def test_rrf_rewards_agreement_between_rankings(self):
        fused = [k for k, _ in rrf([["a", "b", "c"], ["c", "a", "d"]])]
        self.assertEqual(fused[:2], ["a", "c"])
        self.assertEqual(set(fused), {"a", "b", "c", "d"})

    def test_rrf_keeps_an_item_only_one_list_found(self):
        self.assertIn("z", [k for k, _ in rrf([["a"], ["z"]])])

    def test_vector_and_keyword_rank(self):
        e = HashingEmbedder(128)
        docs = {1: "annual leave is 25 days", 2: "the pump is blocked", 3: "hotel limit is 180 USD"}
        vecs = dict(zip(docs, e.embed_documents(list(docs.values()))))
        self.assertEqual(vector_rank(e.embed_query("how many leave days"), vecs.items(), k=1)[0][0], 1)
        self.assertEqual(keyword_rank("hotel limit", docs, k=1)[0][0], 3)
        self.assertEqual(keyword_rank("zebra", docs), [])

    def test_per_document_cap_near_duplicates_and_budget(self):
        doc_of = {1: "A", 2: "A", 3: "A", 4: "B"}.get
        self.assertEqual(limit_per_group([1, 2, 3, 4], doc_of, 2), [1, 2, 4])
        vecs = {1: [1.0, 0.0], 2: [0.999, 0.01], 3: [0.0, 1.0]}
        self.assertEqual(drop_near_duplicates([1, 2, 3], vecs, 0.97), [1, 3])
        tokens = {1: 100, 2: 100, 3: 100}.get
        self.assertEqual(fit_to_budget([1, 2, 3], tokens, 250), [1, 2])
        self.assertEqual(fit_to_budget([1, 2], {1: 900, 2: 1}.get, 100), [1])

    def test_gate(self):
        self.assertTrue(should_answer(0.4, 0.3))
        self.assertFalse(should_answer(0.1, 0.3))


def chunk(i, text="Annual leave is 25 days. You may carry over 5 days.", doc=1, page=1):
    return RetrievedChunk(i, doc, "Handbook", page, page, text)


class PromptingTests(unittest.TestCase):
    def test_sentences_become_citable_blocks_with_citations_enabled(self):
        blocks = build_search_results([chunk(7)])[0]
        self.assertEqual(blocks["type"], "search_result")
        self.assertEqual(blocks["source"], "chunk:7")
        self.assertEqual(blocks["title"], "Handbook, p. 1")
        self.assertEqual([b["text"] for b in blocks["content"]], ["Annual leave is 25 days.", "You may carry over 5 days."])
        self.assertEqual(blocks["citations"], {"enabled": True})

    def test_many_sentences_are_grouped_into_at_most_ten_blocks(self):
        text = " ".join(f"Sentence {i} is here." for i in range(25))
        self.assertLessEqual(len(chunk_to_blocks(text)), 10)

    def test_history_is_plain_text_without_markers_and_question_is_last(self):
        history = [{"role": "user", "content": "How much leave?"}, {"role": "assistant", "content": "25 days [1]."}]
        msgs = build_messages("And carry over?", [chunk(7)], history)
        self.assertEqual(msgs[1]["content"], "25 days.")
        self.assertEqual(msgs[-1]["content"][-1], {"type": "text", "text": "And carry over?"})
        self.assertEqual(msgs[-1]["content"][0]["type"], "search_result")

    def test_page_ranges_in_titles(self):
        c = RetrievedChunk(1, 1, "Doc", 3, 4, "x")
        self.assertEqual(c.display_title, "Doc, pp. 3-4")
        self.assertEqual(RetrievedChunk(1, 1, "Doc", None, None, "x").display_title, "Doc")


def api_answer(retrieved):
    """A response shaped like the documented API output for search_result citations."""
    return [
        {"type": "text", "text": "You get "},
        {"type": "text", "text": "25 days of annual leave.", "citations": [{
            "type": "search_result_location", "cited_text": "Annual leave is 25 days.", "source": "chunk:7",
            "title": "Handbook, p. 1", "search_result_index": 0, "start_block_index": 0, "end_block_index": 1}]},
        {"type": "text", "text": " Up to 5 can be carried over. "},
        {"type": "text", "text": "Carry-over is capped at 5 days.", "citations": [{
            "type": "search_result_location", "cited_text": "You may carry over 5 days.", "source": "chunk:7",
            "title": "Handbook, p. 1", "search_result_index": 0, "start_block_index": 1, "end_block_index": 2}]},
    ]


class CitationTests(unittest.TestCase):
    def test_markers_are_numbered_per_chunk_and_quotes_are_collected(self):
        parsed = parse_response(api_answer(None), [chunk(7)])
        self.assertEqual(parsed.text, "You get 25 days of annual leave. [1] Up to 5 can be carried over. Carry-over is capped at 5 days. [1]")
        self.assertEqual(len(parsed.citations), 1)
        self.assertEqual(parsed.citations[0].quotes, ["Annual leave is 25 days.", "You may carry over 5 days."])
        self.assertTrue(parsed.grounded)
        self.assertEqual(parsed.dropped, 0)

    def test_two_chunks_get_two_markers_in_order_of_appearance(self):
        retrieved = [chunk(7), chunk(9, "Hotel limit is 180 USD per night.", page=3)]
        blocks = [{"type": "text", "text": "Hotels: 180 USD.", "citations": [{
            "type": "search_result_location", "cited_text": "Hotel limit is 180 USD per night.", "source": "chunk:9",
            "search_result_index": 1, "start_block_index": 0, "end_block_index": 1}]},
            {"type": "text", "text": " Leave: 25 days.", "citations": [{
                "type": "search_result_location", "cited_text": "Annual leave is 25 days.", "source": "chunk:7",
                "search_result_index": 0, "start_block_index": 0, "end_block_index": 1}]}]
        parsed = parse_response(blocks, retrieved)
        self.assertEqual([(c.marker, c.chunk_id, c.page_start) for c in parsed.citations], [(1, 9, 3), (2, 7, 1)])
        self.assertEqual(parsed.text, "Hotels: 180 USD. [1] Leave: 25 days. [2]")

    def test_a_citation_that_does_not_match_what_we_sent_is_dropped(self):
        bad_index = {"type": "search_result_location", "cited_text": "Annual leave is 25 days.", "source": "chunk:7", "search_result_index": 5}
        wrong_source = {"type": "search_result_location", "cited_text": "Annual leave is 25 days.", "source": "chunk:99", "search_result_index": 0}
        invented = {"type": "search_result_location", "cited_text": "Employees get 90 days.", "source": "chunk:7", "search_result_index": 0}
        wrong_type = {"type": "char_location", "cited_text": "x"}
        blocks = [{"type": "text", "text": "Claim.", "citations": [bad_index, wrong_source, invented, wrong_type]}]
        parsed = parse_response(blocks, [chunk(7)])
        self.assertEqual(parsed.dropped, 4)
        self.assertFalse(parsed.grounded)
        self.assertEqual(parsed.text, "Claim.")

    def test_whitespace_differences_do_not_break_verification(self):
        retrieved = [chunk(7, "Annual leave is 25 days.  You may\ncarry over 5 days.")]
        blocks = [{"type": "text", "text": "x", "citations": [{"type": "search_result_location",
                   "cited_text": "Annual leave is 25 days. You may carry over 5 days.", "source": "chunk:7", "search_result_index": 0}]}]
        self.assertTrue(parse_response(blocks, retrieved).grounded)

    def test_refusal_is_detected_and_ungrounded_answers_are_flagged(self):
        parsed = parse_response([{"type": "text", "text": NO_ANSWER_TEXT}], [chunk(7)])
        self.assertTrue(parsed.refused)
        self.assertFalse(parsed.grounded)
        confident = parse_response([{"type": "text", "text": "Probably 30 days."}], [chunk(7)])
        self.assertFalse(confident.grounded)
        self.assertFalse(confident.refused)

    def test_streamed_events_rebuild_the_same_answer(self):
        events = [
            {"type": "message_start", "message": {"usage": {"input_tokens": 812}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "25 days "}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "of leave."}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "citations_delta", "citation": {
                "type": "search_result_location", "cited_text": "Annual leave is 25 days.", "source": "chunk:7",
                "title": "Handbook, p. 1", "search_result_index": 0, "start_block_index": 0, "end_block_index": 1}}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 17}},
        ]
        asm = StreamAssembler()
        shown = [t for t in (asm.feed(e) for e in events) if t]
        self.assertEqual("".join(shown), "25 days of leave.")
        self.assertEqual((asm.input_tokens, asm.output_tokens), (812, 17))
        parsed = parse_response(asm.content(), [chunk(7)])
        self.assertEqual(parsed.text, "25 days of leave. [1]")


class LimitTests(unittest.TestCase):
    NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    def test_free_plan_blocks_the_31st_question_with_a_reset_date(self):
        ledger, free = InMemoryLedger(), PLANS["free"]
        for _ in range(30):
            consume(ledger, "u1", free, "questions", 1, self.NOW)
        with self.assertRaises(LimitExceeded) as cm:
            consume(ledger, "u1", free, "questions", 1, self.NOW)
        self.assertIn("30 questions", str(cm.exception))
        self.assertIn("2026-12-01", str(cm.exception))

    def test_a_new_month_starts_a_new_count_and_users_are_separate(self):
        ledger, free = InMemoryLedger(), PLANS["free"]
        consume(ledger, "u1", free, "pages", 100, self.NOW)
        with self.assertRaises(LimitExceeded):
            consume(ledger, "u1", free, "pages", 1, self.NOW)
        self.assertEqual(consume(ledger, "u1", free, "pages", 1, datetime(2026, 12, 1, tzinfo=timezone.utc)), 1)
        self.assertEqual(consume(ledger, "u2", free, "pages", 100, self.NOW), 100)

    def test_a_request_bigger_than_the_remaining_quota_is_refused_whole(self):
        ledger, free = InMemoryLedger(), PLANS["free"]
        consume(ledger, "u1", free, "pages", 90, self.NOW)
        with self.assertRaises(LimitExceeded):
            consume(ledger, "u1", free, "pages", 20, self.NOW)
        self.assertEqual(ledger.used("u1", "pages", period_start(self.NOW)), 90)

    def test_fifty_simultaneous_requests_cannot_exceed_the_limit(self):
        ledger, free = InMemoryLedger(), PLANS["free"]
        results = []

        def worker():
            try:
                consume(ledger, "u1", free, "questions", 1, self.NOW)
                results.append(True)
            except LimitExceeded:
                results.append(False)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sum(results), 30)

    def test_refund_after_a_failed_ingestion(self):
        ledger, free = InMemoryLedger(), PLANS["free"]
        consume(ledger, "u1", free, "pages", 40, self.NOW)
        ledger.refund("u1", "pages", 40, period_start(self.NOW))
        self.assertEqual(ledger.used("u1", "pages", period_start(self.NOW)), 0)

    def test_billable_pages(self):
        self.assertEqual(billable_pages([Page(1, "a"), Page(2, "b")]), 2)
        self.assertEqual(billable_pages([Page(None, "x" * 3001)]), 2)
        self.assertEqual(billable_pages([Page(None, "x")]), 1)

    def test_period_helpers_and_upload_checks(self):
        self.assertEqual(next_reset(datetime(2026, 12, 15, tzinfo=timezone.utc)), datetime(2027, 1, 1, tzinfo=timezone.utc))
        free = PLANS["free"]
        check_upload(free, 5 * 1024 * 1024, current_documents=4)
        with self.assertRaises(LimitExceeded):
            check_upload(free, 5 * 1024 * 1024, current_documents=5)
        with self.assertRaises(LimitExceeded):
            check_upload(free, 11 * 1024 * 1024, current_documents=0)
        with self.assertRaises(ValueError):
            consume(InMemoryLedger(), "u", free, "pages", 0)


class EvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder = HashingEmbedder()
        cls.index = evals.build_index(CORPUS, cls.embedder, target_tokens=60, max_tokens=100, min_tokens=15)
        with open(os.path.join(HERE, "fixtures", "eval_cases.json")) as fh:
            cls.cases = json.load(fh)

    def test_corpus_is_indexed_with_page_numbers(self):
        self.assertGreater(len(self.index), 20)
        self.assertEqual({c.page for c in self.index}, {1, 2, 3})
        self.assertEqual({c.doc for c in self.index}, {"employee_handbook.txt", "security_policy.txt", "product_manual.txt"})

    def test_hybrid_retrieval_quality_meets_the_bar(self):
        r = evals.evaluate(self.index, self.embedder, self.cases, "hybrid")
        self.assertGreaterEqual(r.hit_at[3], 0.95)
        self.assertGreaterEqual(r.mrr, 0.9)

    def test_no_answer_gate_separates_most_questions(self):
        r = evals.evaluate(self.index, self.embedder, self.cases, "hybrid")
        threshold, accuracy = evals.best_threshold(r.sims_answerable, r.sims_unanswerable)
        self.assertGreaterEqual(accuracy, 0.9)
        self.assertGreater(threshold, max(r.sims_unanswerable) - 0.1)

    def test_rank_returns_best_similarity_for_gating(self):
        ranked, sim = evals.rank(self.index, self.embedder, "What is the capital of Australia?", "hybrid", 3)
        self.assertLess(sim, 0.1)


if __name__ == "__main__":
    unittest.main()
