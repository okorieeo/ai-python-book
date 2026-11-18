import json
import unittest

from .candidates import candidate_case
from .sampling import needs_review, review_percent
from .service import (FeedbackError, FeedbackRecord, MessageNotFound, MessageRef, submit_feedback)


class MemStore:
    def __init__(self, refs):
        self.refs = {r.message_id: r for r in refs}
        self.rows = {}

    def get_message(self, mid):
        return self.refs.get(mid)

    def upsert(self, rec):
        created = (rec.user_id, rec.message_id) not in self.rows
        self.rows[(rec.user_id, rec.message_id)] = rec
        return created


def store():
    return MemStore([MessageRef(10, 1, 7, "assistant", "complete"), MessageRef(11, 1, 7, "user", "complete"),
                     MessageRef(12, 2, 8, "assistant", "complete"), MessageRef(13, 1, 7, "assistant", "streaming"),
                     MessageRef(14, 1, 7, "assistant", "refused")])


class SubmitTests(unittest.TestCase):
    def test_thumbs_up_needs_no_reason_and_drops_one_if_given(self):
        s = store()
        rec = submit_feedback(s, user_id=7, message_id=10, rating=1, reason="wrong")
        self.assertEqual((rec.rating, rec.reason), (1, ""))

    def test_thumbs_down_needs_a_known_reason(self):
        s = store()
        for bad in ("", "bad vibes", None):
            with self.subTest(bad=bad), self.assertRaises(FeedbackError):
                submit_feedback(s, user_id=7, message_id=10, rating=-1, reason=bad)
        self.assertEqual(submit_feedback(s, user_id=7, message_id=10, rating=-1, reason="wrong").reason, "wrong")

    def test_rating_must_be_exactly_plus_or_minus_one(self):
        for bad in (0, 2, "1", None, True, 1.5):
            with self.subTest(bad=bad), self.assertRaises(FeedbackError):
                submit_feedback(store(), user_id=7, message_id=10, rating=bad, reason="wrong")

    def test_someone_elses_message_is_indistinguishable_from_a_missing_one(self):
        s = store()
        for mid in (12, 999):
            with self.subTest(mid=mid), self.assertRaises(MessageNotFound):
                submit_feedback(s, user_id=7, message_id=mid, rating=1)

    def test_only_finished_assistant_messages_can_be_rated(self):
        s = store()
        for mid in (11, 13):
            with self.subTest(mid=mid), self.assertRaises(MessageNotFound):
                submit_feedback(s, user_id=7, message_id=mid, rating=1)
        submit_feedback(s, user_id=7, message_id=14, rating=-1, reason="unhelpful")    # a refusal can be rated

    def test_comment_is_scrubbed_trimmed_and_capped(self):
        rec = submit_feedback(store(), user_id=7, message_id=10, rating=-1, reason="wrong",
                              comment="  mail me at ada@example.com " + "x" * 800)
        self.assertIn("[EMAIL]", rec.comment)
        self.assertNotIn("ada@example.com", rec.comment)
        self.assertEqual(len(rec.comment), 500)
        with self.assertRaises(FeedbackError):
            submit_feedback(store(), user_id=7, message_id=10, rating=1, comment=123)

    def test_resubmitting_replaces_instead_of_duplicating(self):
        s = store()
        submit_feedback(s, user_id=7, message_id=10, rating=-1, reason="wrong")
        submit_feedback(s, user_id=7, message_id=10, rating=1)
        self.assertEqual(len(s.rows), 1)
        self.assertEqual(s.rows[(7, 10)].rating, 1)

    def test_consent_defaults_to_no(self):
        self.assertFalse(submit_feedback(store(), user_id=7, message_id=10, rating=1).may_use_for_improvement)


class SamplingTests(unittest.TestCase):
    def test_priorities(self):
        self.assertEqual(review_percent(status="complete", rating=-1, base_percent=2), 100)
        self.assertEqual(review_percent(status="refused", rating=None, base_percent=2), 50)
        self.assertEqual(review_percent(status="complete", rating=1, base_percent=2), 2)
        self.assertEqual(review_percent(status="failed", rating=None, base_percent=80), 80)

    def test_every_thumbs_down_is_reviewed(self):
        self.assertTrue(all(needs_review(i, status="complete", rating=-1) for i in range(500)))

    def test_base_rate_is_respected_and_stable(self):
        picks = [needs_review(i, status="complete", rating=None, base_percent=5) for i in range(20_000)]
        self.assertAlmostEqual(sum(picks) / len(picks), 0.05, delta=0.01)
        self.assertEqual(picks[:200], [needs_review(i, status="complete", rating=None, base_percent=5) for i in range(200)])


class CandidateTests(unittest.TestCase):
    MSGS = [("user", "my email is ada@example.com"), ("assistant", "ok"), ("user", "What is 2+2?"), ("assistant", "5")]

    def fb(self, **kw):
        base = dict(user_id=7, message_id=44, conversation_id=1, rating=-1, reason="wrong", comment="it said 5",
                    may_use_for_improvement=True)
        base.update(kw)
        return FeedbackRecord(**base)

    def test_without_consent_nothing_is_produced(self):
        self.assertIsNone(candidate_case(self.MSGS, 3, self.fb(may_use_for_improvement=False)))

    def test_thumbs_up_is_not_a_candidate(self):
        self.assertIsNone(candidate_case(self.MSGS, 3, self.fb(rating=1)))

    def test_builds_a_scrubbed_draft_that_needs_review(self):
        obj = json.loads(candidate_case(self.MSGS, 3, self.fb()))
        self.assertEqual(obj["id"], "fb-44")
        self.assertEqual(obj["input"], "What is 2+2?")
        self.assertEqual(obj["history"][0], ["user", "my email is [EMAIL]"])
        self.assertTrue(obj["needs_review"])
        self.assertEqual(obj["bad_answer"], "5")
        self.assertIn("reason-wrong", obj["tags"])
        self.assertNotIn("checks", obj)                 # a human must write the expectation

    def test_pointing_at_the_wrong_message_is_a_bug(self):
        for idx in (0, 2, 9):
            with self.subTest(idx=idx), self.assertRaises(ValueError):
                candidate_case(self.MSGS, idx, self.fb())


if __name__ == "__main__":
    unittest.main()
