"""Run: python -m unittest core.review.test_erd_rbac -v"""
import unittest

from core import rbac
from core.review import erd_check as ec

ERD = """
model Conversation
  public_id uuid unique
  user fk User cascade
  title char(200)
  archived_at datetime null
  index (user, -updated_at)
  unique (user, slug)

model Message
  conversation fk Conversation cascade index
  role char(10)
  content text
  created_at datetime index
"""

GOOD = '''
from django.conf import settings
from django.db import models


class Conversation(models.Model):
    public_id = models.UUIDField(unique=True, default=None)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=200)
    slug = models.SlugField()
    archived_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-updated_at"], name="conv_user_updated_idx")]
        constraints = [models.UniqueConstraint(fields=["user", "slug"], name="uniq_conv_user_slug")]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
'''


def diffs(erd=ERD, src=GOOD):
    return ec.compare(ec.parse_erd(erd), ec.parse_django_models(src))


def msgs(found):
    return [d.message for d in found if d.level != "info"]


class ErdParseTests(unittest.TestCase):
    def test_parse(self):
        m = ec.parse_erd(ERD)
        self.assertEqual(set(m), {"Conversation", "Message"})
        c = m["Conversation"]
        self.assertEqual((c.fields["title"].kind, c.fields["title"].length), ("char", 200))
        self.assertEqual((c.fields["user"].target, c.fields["user"].on_delete), ("User", "cascade"))
        self.assertTrue(c.fields["archived_at"].null)
        self.assertEqual(c.indexes, [("user", "-updated_at")])
        self.assertEqual(c.uniques, [("user", "slug")])

    def test_syntax_errors(self):
        for bad in ("Conversation\n  title char(10)\n", "  title char(10)\n", "model A\n  title nonsense\n",
                    "model A\n  title char(10) bogus\n", "model A\n  user fk\n", "model A\n  title\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(ec.ErdSyntaxError):
                    ec.parse_erd(bad)

    def test_comments_and_blank_lines(self):
        m = ec.parse_erd("# header\n\nmodel A  # trailing\n  x int  # note\n")
        self.assertIn("x", m["A"].fields)


class ErdCompareTests(unittest.TestCase):
    def test_matching_models_have_no_errors(self):
        self.assertEqual(msgs(diffs()), [])

    def test_missing_model_and_field(self):
        self.assertIn("model is in the ERD but not in models.py", msgs(diffs(src=GOOD.split("class Message")[0])))
        self.assertIn("field title is missing", msgs(diffs(src=GOOD.replace("    title = models.CharField(max_length=200)\n", ""))))

    def test_type_and_length_mismatch(self):
        self.assertTrue(any("ERD says char, model has TextField" in m for m in msgs(diffs(src=GOOD.replace("CharField(max_length=200)", "TextField()")))))
        self.assertTrue(any("max_length is 100, ERD says 200" in m for m in msgs(diffs(src=GOOD.replace("max_length=200", "max_length=100")))))

    def test_fk_target_and_on_delete(self):
        self.assertTrue(any("on_delete is set_null, ERD says cascade" in m for m in msgs(diffs(src=GOOD.replace("on_delete=models.CASCADE, related_name=\"conversations\"", "on_delete=models.SET_NULL, related_name=\"conversations\"")))))
        self.assertTrue(any("points at Message, ERD says Conversation" in m for m in msgs(diffs(src=GOOD.replace("ForeignKey(Conversation,", "ForeignKey(Message,")))))

    def test_unique_and_index_and_null(self):
        self.assertTrue(any("public_id: ERD says unique" in m for m in msgs(diffs(src=GOOD.replace("UUIDField(unique=True, default=None)", "UUIDField()")))))
        self.assertTrue(any("created_at: ERD says indexed" in m for m in msgs(diffs(src=GOOD.replace(", db_index=True", "")))))
        self.assertTrue(any("archived_at: null=False but the ERD says nullable" in m for m in msgs(diffs(src=GOOD.replace("DateTimeField(null=True, blank=True)", "DateTimeField()")))))
        self.assertTrue(any("null=True but the ERD says required" in m for m in msgs(diffs(src=GOOD.replace("role = models.CharField(max_length=10)", "role = models.CharField(max_length=10, null=True)")))))

    def test_composite_index_and_unique_constraint(self):
        no_meta = GOOD.split("    class Meta:")[0] + "\n\nclass Message" + GOOD.split("class Message")[1]
        found = msgs(diffs(src=no_meta))
        self.assertIn("missing index on (user, -updated_at)", found)
        self.assertIn("missing unique constraint on (user, slug)", found)

    def test_foreign_keys_are_indexed_by_default(self):
        self.assertEqual([m for m in msgs(diffs()) if "conversation" in m], [])

    def test_extra_fields_and_models_are_notes_not_errors(self):
        extra = GOOD + "\n\nclass Extra(models.Model):\n    a = models.IntegerField()\n"
        found = diffs(src=extra)
        self.assertIn("model is in models.py but not in the ERD", [d.message for d in found if d.level == "info"])
        self.assertTrue(any(d.level == "info" and "field slug is in the model" in d.message for d in found))
        self.assertEqual(msgs(found), [])

    def test_non_model_classes_are_ignored(self):
        self.assertEqual(ec.parse_django_models("class Helper:\n    x = 1\n"), {})


class RbacTests(unittest.TestCase):
    def test_deny_by_default(self):
        self.assertFalse(rbac.can(None, "conversation.read"))
        self.assertFalse(rbac.can("hacker", "conversation.read"))
        self.assertFalse(rbac.can("owner", "nonexistent.action"))
        self.assertFalse(rbac.can("viewer", "message.send"))

    def test_role_capabilities(self):
        self.assertTrue(rbac.can("member", "message.send"))
        self.assertFalse(rbac.can("member", "workspace.invite"))
        self.assertTrue(rbac.can(rbac.Role.ADMIN, "workspace.invite"))
        self.assertFalse(rbac.can("admin", "workspace.billing.manage"))
        self.assertTrue(rbac.can("owner", "workspace.billing.manage"))

    def test_ladder_is_consistent(self):
        self.assertTrue(rbac.privilege_ladder_ok())

    def test_every_listed_permission_is_a_known_action(self):
        for role, perms in rbac.PERMISSIONS.items():
            self.assertLessEqual(perms, set(rbac.ACTIONS), role)

    def test_matrix_gaps(self):
        routes = {"GET /conversations": "conversation.read", "POST /conversations": "conversation.create",
                  "DELETE /conversations/<id>": None, "POST /invites": "workspace.inviite"}
        gaps = rbac.matrix_gaps(routes)
        self.assertEqual(len(gaps), 2)
        self.assertIn("no required action", gaps[0])
        self.assertIn("unknown action", gaps[1])
        self.assertIn("message.send", rbac.unused_actions(routes))


if __name__ == "__main__":
    unittest.main()
