"""Tests for the framework-independent code of Chapter 34. Run: python -m unittest core.test_responsible -v"""
import json
import unittest
import zipfile
import io
from datetime import datetime, timedelta, timezone

from core.responsible import bias, citations, consent_logic as cl, data_inventory as di
from core.responsible import erasure, export, pii, retention, safety

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


class PseudonymizerTests(unittest.TestCase):
    def test_email_is_replaced_and_restored(self):
        p = pii.Pseudonymizer()
        out = p.apply("Write to ada@example.com today")
        self.assertEqual(out, "Write to [EMAIL_1] today")
        self.assertEqual(p.restore("Sure, I will email [EMAIL_1]."), "Sure, I will email ada@example.com.")

    def test_same_value_same_placeholder_case_insensitive(self):
        p = pii.Pseudonymizer()
        out = p.apply("Ada@Example.com and ada@example.com and bob@example.com")
        self.assertEqual(out, "[EMAIL_1] and [EMAIL_1] and [EMAIL_2]")
        self.assertEqual(p.redaction_count, 2)

    def test_valid_card_number_found_invalid_ignored(self):
        self.assertEqual(pii.Pseudonymizer().apply("card 4111 1111 1111 1111 ok"), "card [CARD_1] ok")
        self.assertEqual(pii.Pseudonymizer().apply("order 4111 1111 1111 1112"), "order 4111 1111 1111 1112")

    def test_luhn(self):
        self.assertTrue(pii.luhn_valid("4111111111111111"))
        self.assertFalse(pii.luhn_valid("4111111111111112"))
        self.assertFalse(pii.luhn_valid("1234"))

    def test_nigerian_and_international_phones(self):
        for number in ("0803 123 4567", "08031234567", "+234 803 123 4567", "+1 (415) 555-0132", "(415) 555-0132"):
            with self.subTest(number=number):
                self.assertEqual(pii.Pseudonymizer().apply(f"call {number} now"), "call [PHONE_1] now")

    def test_ordinary_numbers_are_not_phones(self):
        for text in ("Order 123456789012 shipped", "Date 2026-11-05 14:30", "Total 1,250,000 naira", "v 3.12.3"):
            with self.subTest(text=text):
                self.assertEqual(pii.Pseudonymizer().apply(text), text)

    def test_labelled_ids_keep_the_label(self):
        out = pii.Pseudonymizer().apply("My BVN is 22212345678 and SSN: 123-45-6789")
        self.assertEqual(out, "My BVN is [ID_1] and SSN: [ID_2]")

    def test_eleven_digits_without_a_label_are_not_an_id(self):
        self.assertNotIn("[ID_", pii.Pseudonymizer().apply("ref 22212345678"))

    def test_ip_addresses(self):
        self.assertEqual(pii.Pseudonymizer().apply("from 192.168.1.20 yes"), "from [IP_1] yes")
        self.assertEqual(pii.Pseudonymizer().apply("version 999.1.1.1"), "version 999.1.1.1")

    def test_known_names_via_extra_terms(self):
        p = pii.Pseudonymizer(extra_terms={"Amina Bello": "NAME"})
        self.assertEqual(p.apply("I am amina bello, hello"), "I am [NAME_1], hello")
        self.assertEqual(p.restore("Hi [NAME_1]!"), "Hi amina bello!")

    def test_tiny_terms_are_ignored(self):
        self.assertEqual(pii.Pseudonymizer(extra_terms={"Al": "NAME"}).apply("Also alpha"), "Also alpha")

    def test_card_beats_phone_when_overlapping(self):
        kinds = [f.kind for f in pii.find_pii("4111111111111111")]
        self.assertEqual(kinds, ["CARD"])

    def test_only_selected_kinds(self):
        p = pii.Pseudonymizer(kinds={"EMAIL"})
        self.assertEqual(p.apply("a@b.co 0803 123 4567"), "[EMAIL_1] 0803 123 4567")

    def test_text_without_pii_is_unchanged_and_mapping_empty(self):
        p = pii.Pseudonymizer()
        self.assertEqual(p.apply("Explain recursion"), "Explain recursion")
        self.assertEqual(p.redaction_count, 0)


def ev(purpose, granted, version="v1", minutes=0):
    return cl.ConsentEvent(purpose, granted, version, NOW + timedelta(minutes=minutes))


class ConsentTests(unittest.TestCase):
    P = cl.Purpose

    def test_no_events_means_no_consent(self):
        self.assertFalse(cl.has_consent([], self.P.ANALYTICS))

    def test_grant_then_withdraw(self):
        events = [ev(self.P.ANALYTICS, True, minutes=0), ev(self.P.ANALYTICS, False, minutes=5)]
        self.assertFalse(cl.has_consent(events, self.P.ANALYTICS))

    def test_withdraw_then_grant_again(self):
        events = [ev(self.P.ANALYTICS, False, minutes=0), ev(self.P.ANALYTICS, True, minutes=5)]
        self.assertTrue(cl.has_consent(events, self.P.ANALYTICS))

    def test_order_in_list_does_not_matter_only_time(self):
        events = [ev(self.P.ANALYTICS, False, minutes=5), ev(self.P.ANALYTICS, True, minutes=0)]
        self.assertFalse(cl.has_consent(events, self.P.ANALYTICS))

    def test_tie_goes_to_later_item(self):
        events = [ev(self.P.IMPROVEMENT, True), ev(self.P.IMPROVEMENT, False)]
        self.assertFalse(cl.has_consent(events, self.P.IMPROVEMENT))

    def test_purposes_are_independent(self):
        events = [ev(self.P.ANALYTICS, True)]
        self.assertFalse(cl.has_consent(events, self.P.MARKETING))

    def test_version_mismatch_is_not_consent(self):
        events = [ev(self.P.IMPROVEMENT, True, "v1")]
        self.assertTrue(cl.has_consent(events, self.P.IMPROVEMENT, required_version="v1"))
        self.assertFalse(cl.has_consent(events, self.P.IMPROVEMENT, required_version="v2"))

    def test_missing_required_lists_changed_documents(self):
        versions = {self.P.TERMS: "2026-11", self.P.PRIVACY_NOTICE: "2026-11"}
        events = [ev(self.P.TERMS, True, "2026-11"), ev(self.P.PRIVACY_NOTICE, True, "2026-05")]
        self.assertEqual(cl.missing_required(events, versions), [self.P.PRIVACY_NOTICE])
        self.assertEqual(cl.missing_required([], versions), [self.P.PRIVACY_NOTICE, self.P.TERMS])

    def test_optional_and_required_sets_do_not_overlap(self):
        self.assertFalse(cl.REQUIRED & cl.OPTIONAL)


class RetentionTests(unittest.TestCase):
    def test_boundary_is_inclusive(self):
        self.assertTrue(retention.is_expired(NOW - timedelta(days=30), 30, NOW))
        self.assertFalse(retention.is_expired(NOW - timedelta(days=29, hours=23), 30, NOW))

    def test_none_never_expires(self):
        self.assertFalse(retention.is_expired(NOW - timedelta(days=9999), None, NOW))

    def test_expired_ids_and_legal_hold(self):
        old, new = NOW - timedelta(days=40), NOW - timedelta(days=1)
        records = [(1, old), (2, new), (3, old)]
        self.assertEqual(retention.expired_ids(records, 30, NOW), [1, 3])
        self.assertEqual(retention.expired_ids(records, 30, NOW, legal_hold=frozenset({3})), [1])

    def test_rules_reject_nonpositive_days(self):
        with self.assertRaises(ValueError):
            retention.RetentionRule("x", 0, "bad")

    def test_batches(self):
        self.assertEqual([list(b) for b in retention.batched(list(range(5)), 2)], [[0, 1], [2, 3], [4]])
        with self.assertRaises(ValueError):
            list(retention.batched([1], 0))


class ErasureTests(unittest.TestCase):
    def make(self, fail=()):
        calls = []
        reg = erasure.EraserRegistry()

        def mk(name):
            def run(subject):
                calls.append(name)
                if name in fail:
                    raise ConnectionError("provider down")
                return 3
            return run
        for name in ("conversations", "vectors", "provider_files"):
            reg.register(name, mk(name))
        reg.register("optional_cache", mk("optional_cache"), required=False)
        return reg, calls

    def test_all_succeed(self):
        reg, _ = self.make()
        results = reg.run_all("u1")
        self.assertTrue(all(r.ok for r in results))
        self.assertTrue(reg.is_complete({r.store for r in results if r.ok}))

    def test_one_failure_does_not_stop_the_rest_and_is_reported(self):
        reg, calls = self.make(fail={"vectors"})
        results = reg.run_all("u1")
        self.assertEqual(calls, ["conversations", "vectors", "provider_files", "optional_cache"])
        failed = [r for r in results if not r.ok]
        self.assertEqual([(r.store, r.detail) for r in failed], [("vectors", "ConnectionError")])
        self.assertFalse(reg.is_complete({r.store for r in results if r.ok}))

    def test_retry_runs_only_what_is_left(self):
        reg, calls = self.make(fail={"vectors"})
        first = reg.run_all("u1")
        done = frozenset(r.store for r in first if r.ok)
        calls.clear()
        reg.erasers[1].run = lambda s: calls.append("vectors") or 1  # the provider is back
        second = reg.run_all("u1", already_done=done)
        self.assertEqual(calls, ["vectors"])
        self.assertTrue(reg.is_complete(set(done) | {r.store for r in second if r.ok}))

    def test_optional_eraser_not_needed_for_completion(self):
        reg, _ = self.make()
        self.assertTrue(reg.is_complete({"conversations", "vectors", "provider_files"}))

    def test_duplicate_names_rejected(self):
        reg, _ = self.make()
        with self.assertRaises(ValueError):
            reg.register("vectors", lambda s: 0)

    def test_error_detail_holds_only_the_exception_type(self):
        reg = erasure.EraserRegistry()
        reg.register("x", lambda s: (_ for _ in ()).throw(ValueError("secret@example.com")))
        self.assertEqual(reg.run_all("u")[0].detail, "ValueError")


class ExportTests(unittest.TestCase):
    def sample(self):
        return export.build_export(
            user={"public_id": "u-1", "email": "ada@example.com", "display_name": "Ada", "role": "member",
                  "date_joined": "2026-01-01", "password": "pbkdf2$secret", "is_staff": True},
            consents=[{"purpose": "analytics", "granted": True, "document_version": "v1",
                       "created_at": "2026-02-01", "ip_address": "10.0.0.1"}],
            conversations=[{"public_id": "c-1", "title": "Plan", "created_at": "2026-03-01", "internal_note": "x",
                            "messages": [{"role": "user", "content": "Hi", "created_at": "t", "token_count": 3},
                                         {"role": "assistant", "content": "Hello", "created_at": "t",
                                          "model": "m", "ai_generated": True}]}],
            billing=[{"provider": "paystack", "amount": 5000, "currency": "NGN", "status": "paid",
                      "created_at": "t", "card_last4": "4242", "authorization_code": "AUTH_x"}],
            generated_at=NOW,
        )

    def test_allow_list_drops_sensitive_and_unknown_fields(self):
        text = export.to_json_bytes(self.sample()).decode()
        for secret in ("pbkdf2", "is_staff", "10.0.0.1", "internal_note", "token_count", "AUTH_x", "4242"):
            self.assertNotIn(secret, text)
        self.assertIn("ada@example.com", text)

    def test_json_is_valid_and_versioned(self):
        data = json.loads(export.to_json_bytes(self.sample()))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(len(data["conversations"][0]["messages"]), 2)

    def test_zip_layout(self):
        with zipfile.ZipFile(io.BytesIO(export.to_zip_bytes(self.sample()))) as z:
            self.assertEqual(sorted(z.namelist()), ["README.txt", "conversations/c-1.txt", "data.json"])
            self.assertIn("AI (t):", z.read("conversations/c-1.txt").decode())

    def test_unsafe_conversation_id_cannot_escape_the_archive(self):
        data = self.sample()
        data["conversations"][0]["public_id"] = "../../etc/passwd"
        with zipfile.ZipFile(io.BytesIO(export.to_zip_bytes(data))) as z:
            self.assertTrue(all(".." not in n and not n.startswith("/") for n in z.namelist()))


SRC = [citations.Source(1, "Refund policy", "Refunds are available within 14 days of purchase for annual plans."),
       citations.Source(2, "Limits", "The free plan includes 50 messages per day.")]


class CitationTests(unittest.TestCase):
    def v(self, answer, **kw):
        return citations.verify_citations(answer, SRC, **kw)

    def test_good_answer(self):
        r = self.v('You can ask within 14 days [1]. The free plan has 50 messages a day [2].')
        self.assertTrue(r.ok, r.issues)
        self.assertEqual(r.cited, {1, 2})

    def test_unknown_source(self):
        r = self.v("Yes it is refundable [7].")
        self.assertEqual([i.kind for i in r.issues], ["unknown_source"])

    def test_quote_must_appear_in_the_cited_source(self):
        ok = self.v('The policy says "Refunds are available within 14 days of purchase" [1].')
        self.assertTrue(ok.ok, ok.issues)
        bad = self.v('The policy says "Refunds are always available with no time limit" [1].')
        self.assertEqual([i.kind for i in bad.issues], ["quote_not_found"])

    def test_quote_matching_ignores_case_and_punctuation(self):
        self.assertTrue(self.v('It says "the free plan includes 50 messages per day!" [2].').ok)

    def test_numbers_without_citation_flagged(self):
        r = self.v("You get 500 messages a day.")
        kinds = {i.kind for i in r.issues}
        self.assertIn("no_citations", kinds)

    def test_uncited_number_in_otherwise_cited_answer(self):
        r = self.v("Refunds take 14 days [1]. Support replies within 3 hours.")
        self.assertEqual([i.kind for i in r.issues], ["uncited_number"])

    def test_abstaining_is_allowed(self):
        self.assertTrue(self.v("I could not find that in the documents you shared.").ok)

    def test_citations_optional(self):
        self.assertTrue(self.v("Hello there.", require_citations=False).ok)


class StubClassifier:
    def __init__(self, scores=None, error=False):
        self.scores, self.error, self.calls = scores or {}, error, 0

    def classify(self, text):
        self.calls += 1
        if self.error:
            raise TimeoutError("moderation api down")
        return self.scores


class SafetyTests(unittest.TestCase):
    def pipe(self, **kw):
        return safety.SafetyPipeline(StubClassifier(**kw), safety.SafetyConfig(canary="CANARY-7f3a"))

    def test_normal_text_allowed(self):
        self.assertEqual(self.pipe().check_input("How do I bake bread?").action, safety.Action.ALLOW)

    def test_crisis_phrase_gets_support_without_calling_the_classifier(self):
        p = self.pipe()
        v = p.check_input("I want to die")
        self.assertEqual((v.action, v.category), (safety.Action.SUPPORT, "self_harm"))
        self.assertEqual(p.classifier.calls, 0)

    def test_crisis_detector_cases(self):
        for t in ("i'm thinking of ending my life", "thoughts of Suicide", "I keep hurting myself"):
            self.assertTrue(safety.looks_like_crisis(t), t)
        for t in ("kill the process", "this bug will kill me lol, deadline", "die-cast model"):
            self.assertFalse(safety.looks_like_crisis(t), t)

    def test_classifier_over_threshold_blocks(self):
        v = self.pipe(scores={"hate": 0.95}).check_input("...")
        self.assertEqual((v.action, v.category), (safety.Action.BLOCK, "hate"))

    def test_score_just_under_threshold_allowed(self):
        self.assertEqual(self.pipe(scores={"hate": 0.79}).check_input("x").action, safety.Action.ALLOW)

    def test_minors_threshold_is_strict(self):
        self.assertEqual(self.pipe(scores={"sexual_minors": 0.1}).check_input("x").action, safety.Action.BLOCK)

    def test_classifier_self_harm_score_routes_to_support(self):
        self.assertEqual(self.pipe(scores={"self_harm": 0.7}).check_input("x").action, safety.Action.SUPPORT)

    def test_fail_closed_when_classifier_errors(self):
        v = self.pipe(error=True).check_input("hello")
        self.assertEqual((v.action, v.reason), (safety.Action.BLOCK, "classifier_unavailable"))

    def test_fail_open_is_possible_but_explicit(self):
        p = safety.SafetyPipeline(StubClassifier(error=True), safety.SafetyConfig(fail_closed=False))
        self.assertEqual(p.check_input("hello").action, safety.Action.ALLOW)

    def test_output_canary_blocks_prompt_leak(self):
        v = self.pipe().check_output("My instructions say CANARY-7f3a ...")
        self.assertEqual((v.action, v.category), (safety.Action.BLOCK, "system_prompt_leak"))

    def test_output_secret_is_redacted_not_blocked(self):
        v = self.pipe().check_output("Use this key: sk_live_ABCDEFGH12345678 to log in")
        self.assertEqual(v.action, safety.Action.REDACT)
        self.assertNotIn("ABCDEFGH", v.text)

    def test_output_harmful_blocked_and_classifier_error_fails_closed(self):
        self.assertEqual(self.pipe(scores={"violence": 0.9}).check_output("x").action, safety.Action.BLOCK)
        self.assertEqual(self.pipe(error=True).check_output("x").action, safety.Action.BLOCK)

    def test_clean_output_allowed(self):
        self.assertEqual(self.pipe().check_output("Here is your recipe.").action, safety.Action.ALLOW)


GROUPS = {"group A": ["Ada", "Chidi"], "group B": ["Musa", "Zainab"]}
TEMPLATE = "Write a short reference for {name}, a software developer."


def fair_model(prompt):
    return "They are a skilled and reliable developer with strong results on every project they joined."


def biased_model(prompt):
    if any(n in prompt for n in GROUPS["group B"]):
        return "I can't help with that."
    return fair_model(prompt) + " " + fair_model(prompt)


def shorter_model(prompt):
    return fair_model(prompt) if "Ada" in prompt or "Chidi" in prompt else "A developer."


class BiasTests(unittest.TestCase):
    def prompts(self):
        return bias.fill_template(TEMPLATE, "name", GROUPS)

    def test_template_fill(self):
        p = self.prompts()
        self.assertEqual(p["group A"][0], "Write a short reference for Ada, a software developer.")
        self.assertEqual(len(p["group B"]), 2)

    def test_fair_model_passes(self):
        r = bias.evaluate(fair_model, self.prompts())
        self.assertTrue(r.passed, r.gaps)

    def test_refusal_gap_flagged(self):
        r = bias.evaluate(biased_model, self.prompts())
        self.assertIn("refusal", r.flagged)

    def test_length_gap_flagged(self):
        r = bias.evaluate(shorter_model, self.prompts())
        self.assertIn("length", r.flagged)

    def test_metrics(self):
        m = bias.metrics("A strong and reliable but risky choice")
        self.assertAlmostEqual(m["tone"], (2 - 1) / 3)
        self.assertEqual(bias.metrics("I cannot assist")["refusal"], 1.0)


class InventoryTests(unittest.TestCase):
    ERASERS = {"account", "conversations", "consents", "billing_anonymize", "ai_logs", "flagged", "vectors"}

    def test_shipped_inventory_is_consistent(self):
        problems = di.validate_inventory(di.INVENTORY, registered_erasers=self.ERASERS,
                                         retention_rules=set(retention.RULES))
        self.assertEqual(problems, [])

    def test_problems_are_detected(self):
        bad = (di.DataItem("a.B.c", "content", "x", "contract", True, None, None),
               di.DataItem("a.B.c", "content", "", "legitimate_interest", True, "nope", "ghost"))
        problems = " | ".join(di.validate_inventory(bad, registered_erasers=set(), retention_rules=set()))
        for text in ("listed twice", "live forever", "unknown retention", "not registered",
                     "without contract or consent", "no purpose"):
            self.assertIn(text, problems)


if __name__ == "__main__":
    unittest.main()
