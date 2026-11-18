# Chapter 31 — Retrieval-Augmented Generation (RAG): extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Embeddings and Similarity Search › Choosing an embedding model

Anthropic does not offer its own embedding model. Its documentation points to Voyage AI as the recommended provider, and the examples in this chapter use it. Others exist (OpenAI, Cohere, Google and open models you can run yourself), and the code is written so that you can swap the provider by writing one small class. Choosing a model is a trade between quality, speed, price, languages and vector size. You decide with your own evaluation (31.9), not with a leaderboard.

Facts that matter for the code:

- **Queries and documents are embedded differently.** Voyage's API takes an `input_type`, `"document"` for text you store and `"query"` for the user's question, and uses it to prepare the text. Always set it.
- **Vector size is a setting of the model.** The database column must match it exactly. A mismatch fails loudly, which is good.
- **Never mix models.** Vectors from two different models live in different spaces, and comparing them is meaningless. Store the model name with every chunk, search only chunks from the model you are querying with, and re-embed everything when you change models.
- **Embedding costs tokens.** You pay once per chunk at ingestion and once per question. Batch your requests, because the APIs limit how much one request may carry.
- **Your documents go to a third party.** Text you embed is sent to the provider. Check its data terms, and tell your users (Chapter 34).

## Chunking: Cutting Documents into Pieces › Four rules the code follows

- **Chunks are exact slices of the source.** Every chunk records `start` and `end`, and `text == source[start:end]`. That is what lets the interface highlight the cited passage (31.7).
- **Cut at natural boundaries.** Paragraph, then sentence, then word. Never in the middle of a word.
- **Keep headings with their text.** A heading with nothing under it is not a chunk. The chunker joins it to the section that follows, and it records the heading path (`("Refund Policy", "Eligibility")`) as metadata.
- **No empty chunks, and every chunk is bounded.** The size limit is a character count. A chunk may exceed it by the length of its heading, because the heading stays attached.
Two bugs were found while writing this chunker, and both are in the tests now: a heading directly followed by another heading became a useless chunk of its own, and a heading followed by one very long paragraph was cut off from it. Both made the heading match searches while answering nothing. Test your chunker on your own documents before you trust it.

**rag/chunking.py**

```
"""Splitting documents into chunks that can be embedded, searched and cited.

Every strategy keeps one promise: chunk.text == source[chunk.start:chunk.end]. That lets the
UI highlight the exact passage a citation points to.
"""
import re
from dataclasses import dataclass

def estimate_tokens(text: str) -> int:
    """Rough token count (about 4 characters per token in English). Good enough for budgets."""
    return (len(text) + 3) // 4 if text else 0

@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start: int            # character offsets in the cleaned source text
    end: int
    heading_path: tuple = ()

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

def _trim(text: str, start: int, end: int):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end

def _windows(text: str, start: int, end: int, size: int, overlap: int) -> list:
    """Cut text[start:end] into windows of about `size` characters, on word boundaries."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("size must be at least 1 and overlap must be smaller than size")
    spans, pos = [], start
    while pos < end:
        cut = min(pos + size, end)
        if cut < end:
            space = max(text.rfind(" ", pos + size // 2, cut), text.rfind("\n", pos + size // 2, cut))
            if space > pos:
                cut = space
        s, e = _trim(text, pos, cut)
        if e > s:
            spans.append((s, e))
        if cut >= end:
            break
        nxt = max(cut - overlap, pos + 1)
        while nxt < cut and not text[nxt - 1].isspace():   # start the next window on a word
            nxt += 1
        pos = nxt
    return spans

def _to_chunks(text: str, spans: list, heading_path: tuple = ()) -> list:
    return [Chunk(i, text[s:e], s, e, heading_path) for i, (s, e) in enumerate(spans)]

def fixed_size_chunks(text: str, size: int = 800, overlap: int = 100) -> list:
    """Windows of about `size` characters that overlap by `overlap`. Simple and predictable."""
    return _to_chunks(text, _windows(text, 0, len(text), size, overlap))

_BLANK_LINE = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

def _paragraph_spans(text: str, start: int, end: int) -> list:
    spans, pos = [], start
    for match in _BLANK_LINE.finditer(text, start, end):
        s, e = _trim(text, pos, match.start())
        if e > s:
            spans.append((s, e))
        pos = match.end()
    s, e = _trim(text, pos, end)
    if e > s:
        spans.append((s, e))
    return spans

def _sentence_spans(text: str, start: int, end: int) -> list:
    spans, pos = [], start
    for match in _SENTENCE_END.finditer(text, start, end):
        s, e = _trim(text, pos, match.start())
        if e > s:
            spans.append((s, e))
        pos = match.end()
    s, e = _trim(text, pos, end)
    if e > s:
        spans.append((s, e))
    return spans

def _pack(text: str, pieces: list, max_chars: int, split_long) -> list:
    """Greedily join neighbouring pieces up to max_chars. Oversized pieces are split further."""
    spans, cur_s, cur_e = [], None, None

    def flush():
        nonlocal cur_s, cur_e
        if cur_s is not None:
            spans.append((cur_s, cur_e))
        cur_s = cur_e = None

    for s, e in pieces:
        if e - s > max_chars:
            flush()
            spans.extend(split_long(s, e))
        elif cur_s is not None and e - cur_s > max_chars:
            flush()
            cur_s, cur_e = s, e
        elif cur_s is None:
            cur_s, cur_e = s, e
        else:
            cur_e = e
    flush()
    return spans

def _recursive_spans(text: str, start: int, end: int, max_chars: int) -> list:
    """Paragraphs first, then sentences, then plain windows: the most natural boundary that fits."""
    def split_paragraph(s, e):
        return _pack(text, _sentence_spans(text, s, e), max_chars,
                     lambda a, b: _windows(text, a, b, max_chars, 0))
    return _pack(text, _paragraph_spans(text, start, end), max_chars, split_paragraph)

def paragraph_chunks(text: str, max_chars: int = 1000) -> list:
    """Keep paragraphs together; split long ones at sentences, then at words."""
    return _to_chunks(text, _recursive_spans(text, 0, len(text), max_chars))

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)

def markdown_chunks(text: str, max_chars: int = 1000) -> list:
    """Split at Markdown headings, then paragraphs. Each chunk records the headings above it.

    A heading always stays with the text below it, so a chunk can be longer than max_chars by the
    length of its heading.
    """
    marks = [(m.start(), len(m.group(1)), m.group(2)) for m in _HEADING.finditer(text)]
    sections, stack = [], []
    first = marks[0][0] if marks else len(text)
    if first > 0:
        sections.append((0, first, ()))
    for i, (pos, level, title) in enumerate(marks):
        stack = [(lv, t) for lv, t in stack if lv < level] + [(level, title)]
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections.append((pos, stop, tuple(t for _, t in stack)))
    # A heading with no text of its own ("# Guide" directly followed by "## Setup") would become a
    # useless chunk that matches searches and answers nothing. Join it to the section after it.
    merged, carry = [], None
    for s, e, path in sections:
        s = carry if carry is not None else s
        carry = None
        has_body = any(not line.lstrip().startswith("#") for line in text[s:e].splitlines() if line.strip())
        if not has_body and (s, e, path) != sections[-1]:
            carry = s
            continue
        merged.append((s, e, path))
    chunks = []
    for s, e, path in merged:
        spans = _recursive_spans(text, s, e, max_chars)
        # A heading followed by an oversized paragraph is cut off from it by the packer. Put it back
        # with the first piece of text; the chunk may then exceed max_chars by the length of the heading.
        if len(spans) > 1 and all(not l.strip() or l.lstrip().startswith("#") for l in text[spans[0][0]:spans[0][1]].splitlines()):
            spans = [(spans[0][0], spans[1][1])] + spans[2:]
        for cs, ce in spans:
            chunks.append(Chunk(len(chunks), text[cs:ce], cs, ce, path))
    return chunks

def chunk_stats(chunks: list) -> dict:
    """Count and size summary, handy for checking a chunker on your own documents."""
    sizes = [c.tokens for c in chunks]
    return {
        "chunks": len(chunks),
        "avg_tokens": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "max_tokens": max(sizes) if sizes else 0,
        "min_tokens": min(sizes) if sizes else 0,
    }
```

Here is the chunker run on a few help-center pages. The three strategies produce similar sizes on this text. The heading-aware one also records where each chunk sits, and the last two lines show the offset promise holding:

**text verified output**

```text
== 1. The same text, three ways (about 300 characters per chunk)
fixed      {'chunks': 6, 'avg_tokens': 70.8, 'max_tokens': 75, 'min_tokens': 54}
paragraph  {'chunks': 6, 'avg_tokens': 62.7, 'max_tokens': 75, 'min_tokens': 50}
markdown   {'chunks': 7, 'avg_tokens': 53.6, 'max_tokens': 68, 'min_tokens': 45}
           #0 Refund Policy > Eligibility                '# Refund Policy\n\n## Eligibility\n\nM'
           #1 Refund Policy > How to request a refund    '## How to request a refund\n\nOpen S'
           #2 Plans and Pricing                          '# Plans and Pricing\n\nThe Free plan'
           #3 Plans and Pricing                          'The Team Plus plan costs $40 per u'

chunk #2: path=('Plans and Pricing',) chars 505-693
source slice equals chunk text: True
```

To try a chunker on your own file, run `python -m rag.cli chunk yourfile.md --size 800`. Look at the first chunks with your own eyes. It is the cheapest quality check in this chapter.


## Storing Vectors in Postgres with pgvector › Setting up

pgvector must be installed in the database server, then enabled per database. The easiest way in development is a Postgres image that already includes it. Change the image of your `db` service in `docker-compose.yml` to the pgvector build of **the same major Postgres version you already use** (for example `pgvector/pgvector:pg17`; check the tag list), because data directories do not carry over between major versions. Then install the Python package and enable the extension with a migration, so every environment gets it the same way:

**bash terminal**

```bash
pip install pgvector voyageai
```

**knowledge/migrations/0001_enable_pgvector.py (Django, not executed here)**

```
from django.db import migrations
from pgvector.django import VectorExtension

class Migration(migrations.Migration):
    """Runs CREATE EXTENSION IF NOT EXISTS vector. It must come before the model migration."""

    initial = True
    dependencies = []
    operations = [VectorExtension()]
```


## Storing Vectors in Postgres with pgvector › Index choices

Without an index, Postgres compares your query to every vector. That is an **exact** search: perfect results, slower as the table grows. It is fine for thousands of vectors per owner and often the right choice for a small product. An **approximate** index trades a little accuracy for a lot of speed:

| **Index** | **How it works** | **Strengths** | **Watch out for** |
|---|---|---|---|
| **None (exact)** | Compare against every row that passes the filter | Perfect recall, nothing to tune | Slows down with size |
| **HNSW** | A layered graph of neighbours that the search walks | Fast and accurate; no training step; the usual default | Slower to build, uses more memory |
| **IVFFlat** | Groups vectors into lists, searches the nearest lists | Builds faster, uses less memory | Needs data present when built; lower accuracy unless tuned |

The model above uses HNSW with the cosine operator class (`vector_cosine_ops`). The class must match the operator you query with: pgvector has `<->` for Euclidean distance, `<#>` for negative inner product and `<=>` for cosine distance, and an index only helps queries that use its own operator.


## Storing Vectors in Postgres with pgvector › Storage arithmetic

Each dimension is a 4-byte number, so a 1,024-dimension vector takes about 4 KB. One million chunks therefore need about 4 GB for the vectors, before the index and before the text. Do this sum before you choose a model and a retention policy. It is also why some models let you keep fewer dimensions with a small loss of quality, and why storing only the chunks you need matters.

> **The filtered-search trap**
>
> **An approximate index finds nearest neighbours first and applies your** `WHERE owner_id = ...` **afterwards.** If the owner's chunks are a tiny share of the table, the index may return its nearest candidates, discard almost all of them and hand you fewer results than you asked for, or none. Newer pgvector versions (0.8 and later) can keep scanning until enough rows pass the filter (look for "iterative index scans" in the documentation for your version). Other fixes are a partial index per large tenant, partitioning the table, or an exact scan for small owners. Whatever you choose, **test it with two owners in the table**, as the tests in this chapter do for the in-memory store.


## The Ingestion Pipeline with Celery › The stages

| **#** | **Stage** | **What happens and what can go wrong** |
|---|---|---|
| **1** | **Upload** | The view checks size and type, stores the file, creates the document row with status `pending`, and queues the task **after the transaction commits**, so the worker never looks for a row that is not saved yet |
| **2** | **Extract** | Bytes become text. Plain text, Markdown and HTML are handled here. PDFs, scans and images need extra tools (Chapter 32). An unsupported or empty file fails permanently with a message the user can read |
| **3** | **Clean** | Normalize line endings and Unicode, remove control characters, collapse blank runs. Chunk offsets are measured on this cleaned text |
| **4** | **Fingerprint** | Hash the cleaned text together with the embedding model and the chunking settings. If the stored hash matches, stop: the work is already done |
| **5** | **Chunk** | Heading-aware chunks with offsets and heading paths |
| **6** | **Scan** | Look for prompt-injection patterns in each chunk and record a risk level (section 31.8) |
| **7** | **Contextualize** (optional) | One model call per chunk to add a situating sentence. A failure for one chunk must not fail the document |
| **8** | **Embed** | Send chunks to the embedding API in batches, then check the number and size of the vectors you got back |
| **9** | **Store** | Replace the document's old chunks with the new ones in one transaction, and save the fingerprint |
| **10** | **Finish** | Mark the document `ready`, or `failed` with a short, safe error |


## The Ingestion Pipeline with Celery › The pipeline function

All the logic lives in one plain function, so it is easy to test and has no Django in it. The Celery task only reads the file, calls it and records the status:

**rag/ingest.py (the pipeline)**

```
@dataclass
class IngestReport:
    doc_id: str
    status: str            # "ingested" or "unchanged"
    chunks: int = 0
    flagged: int = 0       # chunks with an injection warning
    embedded_tokens: int = 0

def document_hash(text: str, model: str, chunker_name: str) -> str:
    """Changes when the text, the embedding model or the chunking changes: any of them needs a re-index."""
    return hashlib.sha256(f"{model}\n{chunker_name}\n{text}".encode("utf-8")).hexdigest()

def ingest_document(*, doc_id: str, owner_id: str, title: str, text: str, embedder, store,
                    chunker: Callable = markdown_chunks, chunker_name: str = "markdown-1000",
                    contextualizer: Optional[Callable] = None, batch_size: int = 64,
                    max_chars: int = 2_000_000) -> IngestReport:
    """Ingest one document. Safe to run again: unchanged documents are skipped.

    contextualizer(document_text, chunk) -> str adds a short situating sentence to each chunk
    before it is embedded (section 31.6). If it fails for a chunk, that chunk is stored without it.
    """
    text = clean_document_text(text)
    if not text:
        raise IngestError("The document has no text.")
    if len(text) > max_chars:
        raise IngestError(f"The document is longer than {max_chars} characters.")

    fingerprint = document_hash(text, embedder.model, chunker_name)
    if store.document_hash(doc_id) == fingerprint:
        return IngestReport(doc_id, "unchanged")

    chunks = chunker(text)
    if not chunks:
        raise IngestError("The document produced no chunks.")

    contexts = []
    for chunk in chunks:
        try:
            contexts.append((contextualizer(text, chunk) if contextualizer else "").strip())
        except Exception:
            contexts.append("")

    inputs = [(f"{ctx}\n\n{c.text}" if ctx else c.text) for c, ctx in zip(chunks, contexts)]
    vectors = []
    for batch in batched(inputs, batch_size):
        vectors.extend(embedder.embed_documents(batch))
    if len(vectors) != len(chunks) or any(len(v) != embedder.dimensions for v in vectors):
        raise EmbeddingError("The embedder returned the wrong number or size of vectors.")

    records, flagged = [], 0
    for chunk, ctx, vector in zip(chunks, contexts, vectors):
        risk = risk_level(scan_for_injection(chunk.text))
        flagged += risk != "none"
        records.append(ChunkRecord(
            doc_id=doc_id, owner_id=owner_id, index=chunk.index, title=title, text=chunk.text,
            start=chunk.start, end=chunk.end, heading_path=chunk.heading_path, context=ctx,
            embedding=vector, embedding_model=embedder.model, injection_risk=risk,
        ))
    store.replace_document(doc_id, fingerprint, records)
    return IngestReport(doc_id, "ingested", len(records), flagged, sum(len(i) + 3 for i in inputs) // 4)
```

The function returns a small report: how many chunks were stored, how many were flagged, or `unchanged` when the fingerprint matched. Section 31.12 runs it on the demo documents. The Celery task around it handles status, retries and failure messages:

**knowledge/tasks.py (Django and Celery, not executed here)**

```
from celery import shared_task

from rag.embeddings import EmbeddingError
from rag.ingest import IngestError, extract_text, ingest_document

from .models import KnowledgeDocument
from .services import get_embedder
from .store import PgVectorStore

@shared_task(bind=True, autoretry_for=(EmbeddingError,), retry_backoff=True, retry_backoff_max=600,
             retry_jitter=True, max_retries=5, acks_late=True)
def ingest_document_task(self, document_id: int) -> str:
    """Turn an uploaded file into searchable chunks. Safe to run twice for the same document."""
    document = KnowledgeDocument.objects.get(pk=document_id)
    document.status, document.error = KnowledgeDocument.Status.PROCESSING, ""
    document.save(update_fields=["status", "error", "updated_at"])
    try:
        with document.file.open("rb") as handle:
            text = extract_text(handle.read(), document.content_type)
        report = ingest_document(
            doc_id=str(document.pk), owner_id=str(document.owner_id), title=document.title, text=text,
            embedder=get_embedder(), store=PgVectorStore(),
        )
    except IngestError as error:                      # the file itself is the problem: do not retry
        document.status, document.error = KnowledgeDocument.Status.FAILED, str(error)[:300]
        document.save(update_fields=["status", "error", "updated_at"])
        return "failed"
    except EmbeddingError:
        if self.request.retries >= self.max_retries:  # out of retries: tell the user, keep the error short
            document.status, document.error = KnowledgeDocument.Status.FAILED, "The embedding service was unavailable."
            document.save(update_fields=["status", "error", "updated_at"])
            return "failed"
        raise                                          # autoretry_for schedules the next attempt
    document.status = KnowledgeDocument.Status.READY
    document.save(update_fields=["status", "updated_at"])
    return report.status
```

Four details deserve a second look. `autoretry_for=(EmbeddingError,)` retries only the failures that can succeed later. `acks_late=True` means a worker that dies mid-task does not lose the job, which is safe precisely because the task is idempotent. The `except EmbeddingError` branch gives up after the last retry and marks the document `failed`, so it never sits in `processing` forever. And the file is read inside the task, not passed through the queue, so the message stays small.

The tests for ingestion prove the principles above: unchanged text does nothing, changed text replaces old chunks, a new embedding model triggers a re-index, requests are batched, a wrong-sized vector is caught before storing, and one failed contextualization does not fail the document:

**rag/test_rag.py (IngestTests, excerpt)**

```
    def test_ingesting_the_same_text_twice_does_nothing(self):
        report, store = self.ingest()
        again, _ = self.ingest(store=store)
        self.assertEqual(again.status, "unchanged")
        self.assertEqual(store.count(), report.chunks)

    def test_changed_text_replaces_the_old_chunks(self):
        _, store = self.ingest()
        report, _ = self.ingest(store=store, text="# Refund Policy\n\nAll refunds are final.")
        self.assertEqual(report.status, "ingested")
        self.assertEqual(store.count(), 1)

    def test_a_new_embedding_model_triggers_a_re_index(self):
        _, store = self.ingest()
        report, _ = self.ingest(store=store, embedder=HashingEmbedder(dimensions=128))
        self.assertEqual(report.status, "ingested")

    def test_document_hash_depends_on_text_model_and_chunker(self):
        base = document_hash("t", "m", "c")
        self.assertNotEqual(base, document_hash("t2", "m", "c"))
        self.assertNotEqual(base, document_hash("t", "m2", "c"))
        self.assertNotEqual(base, document_hash("t", "m", "c2"))
```


## The Ingestion Pipeline with Celery › Optional: contextual retrieval

The `contextualizer` argument is the hook for the technique from section 31.3. `make_contextualizer` builds a function that sends each chunk and a window of its document to a model (the `contextualize_chunk` prompt) and returns one or two sentences. Both pieces of text go into the prompt as untrusted data (Chapter 28), because the document is third-party text. It costs one model call per chunk, so use a small, cheap model, and prompt caching (Chapter 33) because every chunk of one document shares the same document text. Run it on a sample and compare retrieval numbers with and without it before you decide it is worth the bill:

**rag/contextual.py**

```
def document_window(text: str, start: int, end: int, budget: int = 12000) -> str:
    """The part of the document around a chunk, small enough for a prompt.

    Short documents are returned whole. For long ones we keep the beginning (titles, intro) and
    the text around the chunk.
    """
    if len(text) <= budget:
        return text
    head = text[: budget // 4]
    room = budget - len(head)
    left = max(len(head), start - room // 2)
    right = min(len(text), left + room)
    return head + "\n[...]\n" + text[left:right]

def make_contextualizer(llm, registry, *, max_chars: int = 400) -> Callable:
    """Build the function that ingest_document calls for each chunk.

    It asks the model for a short sentence that situates the chunk in its document. The sentence
    is added to the chunk BEFORE embedding and keyword indexing, and is not shown to users.
    Costs one model call per chunk, so use a small model (and prompt caching, Chapter 33).
    """
    template = registry.get("contextualize_chunk")

    def contextualize(document_text: str, chunk) -> str:
        prompt = template.render({
            "document": document_window(document_text, chunk.start, chunk.end),
            "chunk": chunk.text,
        })
        reply = llm.complete(system=prompt.system, messages=prompt.messages, max_tokens=150)
        return " ".join(reply.text.split())[:max_chars]

    return contextualize
```


## Retrieval: Getting the Right Chunks › Step 3: Merge with reciprocal rank fusion

You now have two ranked lists with scores on different scales: cosine similarity near 0.4 and BM25 near 1.6. Averaging them would be nonsense. **Reciprocal rank fusion (RRF)** ignores the scores and uses only the ranks: an item at rank r in a list earns `1 / (60 + r)` from that list, and the earnings add up. The constant 60 is the common default. An item that both searches like rises to the top, and nothing needs tuning.

*(figure: see the printed book)*

The module also has MMR (maximal marginal relevance), a way to avoid returning five near-identical chunks: pick results that are relevant **and** different from the ones already chosen.

**rag/fusion.py**

```
"""Combining ranked lists (reciprocal rank fusion) and removing near-duplicates (MMR)."""
from .embeddings import cosine

def reciprocal_rank_fusion(rankings: list, k: int = 60) -> list:
    """Merge several best-first lists of keys into one list of (key, score).

    An item at rank r (starting at 1) in a list earns 1 / (k + r) from that list. Items that
    appear in several lists add up. Only ranks matter, never the raw scores, so lists with
    different scales (cosine similarity and BM25) combine without any tuning. Ties keep the
    order in which items first appeared.
    """
    scores, first_seen = {}, {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(key, len(first_seen))
    return sorted(scores.items(), key=lambda item: (-item[1], first_seen[item[0]]))

def mmr(candidates: list, k: int, lambda_: float = 0.7) -> list:
    """Maximal marginal relevance: pick results that are relevant AND different from each other.

    candidates: [(key, vector, relevance)] best first. lambda_ 1.0 means pure relevance, lower
    values punish similarity to what was already chosen. Returns the chosen keys in order.
    """
    remaining = list(candidates)
    chosen = []
    while remaining and len(chosen) < k:
        def value(item):
            _key, vector, relevance = item
            redundancy = max((cosine(vector, c[1]) for c in chosen), default=0.0)
            return lambda_ * relevance - (1 - lambda_) * redundancy
        best = max(remaining, key=value)
        chosen.append(best)
        remaining.remove(best)
    return [c[0] for c in chosen]
```

Real output for the worked example in the picture, followed by one question run in all three modes. The question is "Is single sign-on available?". Vector search alone returns nothing above the similarity floor, keyword search finds the right page through its rare words, and hybrid keeps it:

**text verified output**

```text
== 4. Reciprocal rank fusion, worked example (k = 60)
plans      0.0328   vector rank 1, keyword rank 1
languages  0.0320   vector rank 3, keyword rank 2
security   0.0161   vector rank 2, keyword rank -
export     0.0159   vector rank -, keyword rank 3

== 5. One question, three retrieval modes: 'Is single sign-on available?'
vector   []
keyword  ['plans', 'languages', 'security']
hybrid   ['plans', 'languages', 'security']
```


## Generating Grounded Answers › The whole path

The pipeline ties the steps together and makes the policy decisions explicit. Read its return values as a list of reasons the system may decline to give a grounded answer:

| **refused_reason** | **What happened** |
|---|---|
| `empty_question` | Nothing to search for. No model call |
| `no_relevant_sources` | Retrieval found nothing above the thresholds. **No model call**: cheaper and safer than asking a model to answer from nothing |
| `model_output_invalid` | The reply could not be turned into valid JSON, even after a retry |
| `model_found_nothing` | The model looked at the sources and said they do not contain the answer. This is a good outcome, shown to the user as is |
| `unverified_citations` | The model claimed an answer but no citation survived verification. **The answer is not shown as grounded** |
| (empty) | A grounded answer with at least one verified citation |

**rag/pipeline.py**

```
"""The whole question-answering path: rewrite, retrieve, build sources, ask, verify."""
from dataclasses import dataclass, field
from typing import Optional

from prompts.blocks import clean_prompt_text
from prompts.runner import run_prompt
from prompts.structured import StructuredOutputError

from .answering import ANSWER_SCHEMA, NOT_FOUND_ANSWER, link_citations, verify_citations
from .context import build_sources
from .contextual import rewrite_query

@dataclass
class RagAnswer:
    answer: str
    found: bool
    citations: list = field(default_factory=list)      # [CitationLink], verified only
    problems: list = field(default_factory=list)       # what verification or checks complained about
    hits: list = field(default_factory=list)
    refused_reason: str = ""                            # why we did not give a grounded answer
    search_query: str = ""
    record: Optional[dict] = None                       # prompt id, tokens, latency (no text)

def _refuse(reason: str, query: str, hits=None, problems=None, record=None) -> RagAnswer:
    return RagAnswer(NOT_FOUND_ANSWER, False, [], problems or [], hits or [], reason, query, record)

def answer_question(question: str, *, owner_id: str, retriever, registry, llm, history: Optional[list] = None,
                    product_name: str = "AI Chat", recorder=None, max_source_chars: int = 12000) -> RagAnswer:
    """Answer from this owner's documents, or say that the answer is not there.

    The model is only called when retrieval found something. An answer is returned as grounded
    only if it has at least one citation whose quote was verified in the retrieved text.
    """
    question = clean_prompt_text(question, max_chars=2000)
    if not question:
        return _refuse("empty_question", "")

    query = rewrite_query(llm, registry, question, history or [])
    hits = retriever.search(query, owner_id)
    if not hits:
        return _refuse("no_relevant_sources", query)

    bundle = build_sources(hits, max_chars=max_source_chars)
    try:
        result = run_prompt(
            registry, llm, "answer_from_sources",
            {"product_name": product_name, "sources": bundle.text, "question": question},
            schema=ANSWER_SCHEMA, recorder=recorder, max_tokens=700,
        )
    except StructuredOutputError as error:
        return _refuse("model_output_invalid", query, hits, error.problems)

    data = result.data
    problems = verify_citations(data, bundle) + result.output_problems
    links = link_citations(data, bundle)
    if not data["found"]:
        return RagAnswer(data["answer"], False, [], problems, hits, "model_found_nothing", query, result.record)
    if not links:
        return _refuse("unverified_citations", query, hits, problems, result.record)
    return RagAnswer(data["answer"], True, links, problems, hits, "", query, result.record)
```

Real output from the tour script. The first answer is verified and linked to character positions in the document. The second question has no relevant source, so the model is never called (the count of model calls is 0). In the third, a scripted model invents a quote, and the check refuses to present the answer as grounded:

**text verified output**

```text
== 7. A grounded answer, a refusal and an invented quote
answer : Approved refunds appear on your card within 5 to 10 business days. [S1]
cite   : [S1] Refund Policy > How to request a refund -> "Approved refunds appear on your card within 5 to 10 business days." (characters 436-502)
refused: found=False reason=no_relevant_sources model_calls=0
invented quote: found=False reason=unverified_citations
problem: citation 1: the quote is not in S1
```

> **What "verified" does and does not mean**
>
> **A verified quote proves that the text exists in a source you provided. It does not prove that the answer is a faithful reading of it.** A model can quote a real sentence and still draw the wrong conclusion. Verification removes fabricated evidence, which is the worst kind, because users trust citations. Faithfulness you measure with evaluation (31.9), and for high-stakes answers you show the quote beside the answer so that the user can judge.


## Generating Grounded Answers › Claude's native citations

Claude's API can produce citations itself. You pass your retrieved chunks as `search_result` content blocks (each with a `source`, a `title` and `content`) and enable citations, and the reply carries citation objects that point into the blocks you supplied. The documentation describes the exact shape. The sketch below is from the docs and was not run here:

**python native citations (syntax from the docs, not executed in this chapter)**

```python
message = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=800,
    messages=[{"role": "user", "content": [
        *[{
            "type": "search_result",
            "source": f"doc:{hit.record.doc_id}",
            "title": hit.record.title,
            "content": [{"type": "text", "text": hit.record.text}],
            "citations": {"enabled": True},
        } for hit in hits],
        {"type": "text", "text": question},
    ]}],
)
# Text blocks in message.content now carry a "citations" list that points at the blocks above.
```

The native feature is convenient because the cited text comes from your content and is not typed by the model. The approach in this chapter works with any provider, combines freely with structured output and fits your own checks and schema. If you consider the native feature, read the current documentation on how it combines with other features such as structured outputs, and keep your own tenant filter and injection defences either way. They do not move into the API.


## Evaluating and Improving a RAG System › A retrieval test set

Write 30 to 100 real questions with the document that contains each answer. Collect them from support tickets, search logs and your own team, and write some in the words users really use, not the words of your documents. Include questions the documents **cannot** answer, to test refusals. Keep a few aside that you never tune against.

| **Metric** | **Meaning** |
|---|---|
| **Hit rate at k** | The share of questions where a relevant document appears in the top k results. The first number to look at |
| **MRR** (mean reciprocal rank) | The average of 1 / rank of the first relevant result: 1.0 if it is always first, 0.5 if always second, 0 when missing. Rewards ranking the answer high |
| **Recall at k** | When a question has several relevant documents, the share found in the top k |
| **Refusal accuracy** | Of the questions with no answer in the documents, the share where the system correctly says so |
| **Citation validity** | The share of answers whose citations all pass verification |

The harness is small. A case is a question, the ids of the relevant documents and the owner who asks. It records the rank of the first relevant document, and a report gives the metrics and lists the misses:

**rag/evaluate.py**

```
"""Measuring retrieval: did the right document come back, and how high did it rank?"""
from dataclasses import dataclass, field

@dataclass
class RetrievalCase:
    question: str
    relevant_docs: frozenset        # doc ids that contain the answer
    owner_id: str = "acme"
    id: str = ""

@dataclass
class CaseOutcome:
    case: RetrievalCase
    rank: int                       # 1-based rank of the first relevant document, 0 if missing
    returned_docs: list = field(default_factory=list)

@dataclass
class RetrievalReport:
    label: str
    k: int
    outcomes: list

    @property
    def hit_rate(self) -> float:
        """Share of questions with a relevant document in the top k (also called recall@k for one answer)."""
        return sum(1 for o in self.outcomes if o.rank) / len(self.outcomes) if self.outcomes else 0.0

    @property
    def mrr(self) -> float:
        """Mean reciprocal rank: 1.0 if the answer is always first, 0.5 if always second, 0 if missing."""
        return sum(1 / o.rank for o in self.outcomes if o.rank) / len(self.outcomes) if self.outcomes else 0.0

    def misses(self) -> list:
        return [o.case.id or o.case.question for o in self.outcomes if not o.rank]

def evaluate_retrieval(retriever, cases: list, *, k: int = 3, mode: str = None, label: str = "") -> RetrievalReport:
    """Run every case through the retriever and record the rank of the first relevant document."""
    outcomes = []
    for case in cases:
        hits = retriever.search(case.question, case.owner_id, k=k, mode=mode)
        docs = []
        for hit in hits:                       # unique documents, in rank order
            if hit.record.doc_id not in docs:
                docs.append(hit.record.doc_id)
        rank = next((i for i, d in enumerate(docs, start=1) if d in case.relevant_docs), 0)
        outcomes.append(CaseOutcome(case, rank, docs))
    return RetrievalReport(label or (mode or retriever.mode), k, outcomes)

def format_comparison(reports: list) -> str:
    """One row per configuration: hit rate, MRR and the questions that missed."""
    lines = [f"{'setting':<10} {'hit@' + str(reports[0].k):>7} {'MRR':>6}  missed", "-" * 64]
    for r in reports:
        missed = ", ".join(r.misses()) or "-"
        lines.append(f"{r.label:<10} {r.hit_rate:>7.2f} {r.mrr:>6.2f}  {missed}")
    return "\n".join(lines)
```


## Evaluating and Improving a RAG System › Real results, with a warning

This is the output of `python -m rag.cli eval` on the 15 demo questions. It compares vector search, keyword search and hybrid search, with the toy embedder:

**text verified output**

```text
== 6. Retrieval evaluation on 15 questions (hit rate and MRR at 3)
setting      hit@3    MRR  missed
----------------------------------------------------------------
vector        0.87   0.87  reimbursed, sso
keyword       0.87   0.87  reimbursed, unsubscribe
hybrid        0.93   0.93  reimbursed
```

**Please read this table for what it is.** The embedder is a toy, so the numbers say nothing about real embedding models. What it does show is how to read an evaluation: the same 15 questions, three settings and a list of the misses. Look at the misses, not only at the totals:

- `sso` ("Is single sign-on available?") was missed by vector search and found by keyword search, because the rare words carry the meaning. Hybrid keeps it.
- `unsubscribe` was missed by keyword search, because the page says "cancel", and found by vector search through the synonym table. Hybrid keeps that too.
- `reimbursed` was missed by all three. The toy stemmer knows `reimburse` but not `reimbursed`, and no document uses the word. A real embedding model would probably handle this one. For a keyword index the fix is a better analyzer. Fixing a miss means first finding out which of these it is.
Run the same evaluation with real embeddings (`python -m rag.cli live`, section 31.12) and expect different numbers and different misses.


## Evaluating and Improving a RAG System › The improvement ladder

Try cheap changes before expensive ones, and re-run the evaluation after **each** one, changing only one thing at a time:

- **1. Fix the documents.** Duplicates, outdated pages, scanned files with no text and missing headings hurt more than any algorithm.
- **2. Fix the chunking.** Look at chunks with your own eyes. Adjust size and use heading-aware splitting.
- **3. Add hybrid search.** Often the largest gain for the least work.
- **4. Add query rewriting** for chat-style questions.
- **5. Tune thresholds and** `k`**.**
- **6. Add a reranker.**
- **7. Try contextual retrieval.** It costs a model call per chunk at ingestion.
- **8. Try a different embedding model**, and re-embed. Only now, because it is the most expensive change to test.
- **9. Last: a larger answer model.** If the right chunks are in the prompt and the answer is still wrong, a stronger model or a better prompt may help.
For answers, check by sampling: read 20 real questions with their sources every week. Add thumbs up and down buttons to the interface and treat every thumbs-down as a candidate evaluation case. Chapter 33 builds the monitoring and the feedback loop around this.
