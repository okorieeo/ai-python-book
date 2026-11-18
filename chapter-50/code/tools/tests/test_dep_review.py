import unittest

from tools import dep_review as dr


def diff(path, *added):
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n" + "".join(f"+{l}\n" for l in added)


class ParseTests(unittest.TestCase):
    def test_requirements(self):
        deps = dr.parse_added_deps(diff("backend/requirements.txt", "requests==2.32.3", "celery>=5", "django-cors-headers", "# comment", "-e git+https://x/y.git#egg=y"))
        names = [(d[2], d[3]) for d in deps]
        self.assertIn(("requests", "==2.32.3"), names)
        self.assertIn(("celery", ">=5"), names)
        self.assertIn(("django-cors-headers", ""), names)
        self.assertTrue(any(d[3] == "url" for d in deps))

    def test_package_json_ignores_scripts_and_metadata(self):
        deps = dr.parse_added_deps(diff("web/package.json", '"name": "web",', '"dev": "next dev",', '"zod": "^3.23.0",', '"@types/react": "19.0.0"'))
        self.assertEqual(sorted(d[2] for d in deps), ["@types/react", "zod"])

    def test_other_files_ignored(self):
        self.assertEqual(dr.parse_added_deps(diff("README.md", "requests==1.0")), [])


class ReviewTests(unittest.TestCase):
    def test_typosquat_names_are_errors(self):
        for path, line in (("requirements.txt", "reqeusts==2.0"), ("requirements.txt", "djanga==5.0"), ("package.json", '"lodahs": "^4.0.0"'),
                           ("package.json", '"expresss": "^4.0.0"')):
            notes = dr.review(diff(path, line))
            self.assertTrue(any(n.startswith("ERROR") for n in notes), (line, notes))

    def test_real_popular_packages_are_not_flagged(self):
        notes = dr.review(diff("requirements.txt", "requests==2.32.3", "Django==5.2") + diff("web/package.json", '"react": "^19.0.0"', '"@types/node": "^22"'))
        self.assertFalse(any(n.startswith("ERROR") for n in notes))
        self.assertFalse(any("not pinned" in n for n in notes))

    def test_name_normalisation(self):
        self.assertFalse(any(n.startswith("ERROR") for n in dr.review(diff("requirements.txt", "Django_Cors_Headers==4.4.0"))))

    def test_unpinned_and_url_sources_warn(self):
        notes = " | ".join(dr.review(diff("requirements.txt", "somepkg>=1.0") + diff("web/package.json", '"foo-bar-baz": "*"', '"qux-lib": "github:someone/qux"')))
        self.assertIn("not pinned", notes)
        self.assertIn("unpinned range", notes)
        self.assertIn("URL or git", notes)

    def test_every_new_package_gets_a_verify_note(self):
        notes = dr.review(diff("requirements.txt", "whatever-lib==1.0"))
        self.assertTrue(any(n.startswith("NEW") for n in notes))

    def test_short_names_need_distance_one(self):
        self.assertIsNone(dr.lookalike("flaky", dr.POPULAR_PYPI))
        self.assertEqual(dr.lookalike("reqests", dr.POPULAR_PYPI), "requests")

    def test_no_dependencies_no_noise(self):
        self.assertEqual(dr.review(diff("backend/views.py", "x = 1")), [])


if __name__ == "__main__":
    unittest.main()
