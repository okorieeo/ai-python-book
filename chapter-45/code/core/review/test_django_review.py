"""Run: python -m unittest core.review.test_django_review -v"""
import tempfile
import unittest
from pathlib import Path

from core.review import django_review as dr


def codes(src, filename="app/views.py"):
    return [f.code for f in dr.review_source(src, filename)]


class SerializerTests(unittest.TestCase):
    def test_all_fields(self):
        src = "class S(serializers.ModelSerializer):\n    class Meta:\n        model = M\n        fields = '__all__'\n"
        self.assertEqual(codes(src), ["DJ001"])

    def test_explicit_fields_ok(self):
        src = "class S(serializers.ModelSerializer):\n    class Meta:\n        model = M\n        fields = ['id', 'title']\n"
        self.assertEqual(codes(src), [])

    def test_exclude(self):
        src = "class S(serializers.ModelSerializer):\n    class Meta:\n        model = M\n        exclude = ['password']\n"
        self.assertEqual(codes(src), ["DJ002"])


class ViewTests(unittest.TestCase):
    def test_missing_permission_classes(self):
        self.assertEqual(codes("class V(APIView):\n    def get(self, request):\n        return 1\n"), ["DJ015"])

    def test_permission_classes_present(self):
        self.assertEqual(codes("class V(APIView):\n    permission_classes = [IsAuthenticated]\n    def get(self, request):\n        return 1\n"), [])

    def test_get_permissions_counts(self):
        src = "class V(ModelViewSet):\n    def get_permissions(self):\n        return []\n"
        self.assertEqual(codes(src), [])

    def test_allow_any(self):
        self.assertEqual(codes("class V(APIView):\n    permission_classes = [AllowAny]\n"), ["DJ016"])

    def test_unscoped_queryset(self):
        src = ("class V(ModelViewSet):\n    permission_classes = [IsAuthenticated]\n"
               "    def get_queryset(self):\n        return Conversation.objects.all()\n")
        self.assertEqual(codes(src), ["DJ003"])

    def test_scoped_queryset_ok(self):
        src = ("class V(ModelViewSet):\n    permission_classes = [IsAuthenticated]\n"
               "    def get_queryset(self):\n        return Conversation.objects.filter(user=self.request.user)\n")
        self.assertEqual(codes(src), [])
        src2 = ("class V(ModelViewSet):\n    permission_classes = [IsAuthenticated]\n"
                "    def get_queryset(self):\n        return Conversation.objects.all().filter(owner=self.request.user)\n")
        self.assertEqual(codes(src2), [])

    def test_tests_are_not_flagged_for_views(self):
        src = "class V(APIView):\n    pass\n"
        self.assertEqual(codes(src, "app/tests/test_views.py"), [])


class SqlTests(unittest.TestCase):
    def test_fstring_raw(self):
        self.assertEqual(codes("def f(n):\n    return Model.objects.raw(f\"SELECT * FROM t WHERE n = {n}\")\n"), ["DJ005"])

    def test_percent_and_concat_and_format(self):
        for expr in ('"SELECT %s" % n', '"SELECT " + n', '"SELECT {}".format(n)'):
            with self.subTest(expr=expr):
                self.assertEqual(codes(f"def f(cursor, n):\n    cursor.execute({expr})\n"), ["DJ005"])

    def test_parameterized_is_fine(self):
        self.assertEqual(codes("def f(cursor, n):\n    cursor.execute('SELECT * FROM t WHERE n = %s', [n])\n"), [])
        self.assertEqual(codes("def f(cursor):\n    cursor.execute('SELECT 1')\n"), [])


class ExceptionTests(unittest.TestCase):
    def test_bare_except(self):
        self.assertEqual(codes("try:\n    x()\nexcept:\n    y()\n"), ["DJ006"])

    def test_swallow_all(self):
        self.assertEqual(codes("try:\n    x()\nexcept Exception:\n    pass\n"), ["DJ006"])

    def test_specific_or_logged_is_fine(self):
        self.assertEqual(codes("try:\n    x()\nexcept KeyError:\n    pass\n"), [])
        self.assertEqual(codes("try:\n    x()\nexcept Exception:\n    log.exception('x')\n"), [])


class PythonPitfallTests(unittest.TestCase):
    def test_mutable_defaults(self):
        self.assertEqual(codes("def f(a, tags=[]):\n    pass\n"), ["DJ007"])
        self.assertEqual(codes("def f(a, tags={}):\n    pass\n"), ["DJ007"])
        self.assertEqual(codes("def f(a, *, tags=dict()):\n    pass\n"), ["DJ007"])
        self.assertEqual(codes("def f(a, tags=None):\n    pass\n"), [])

    def test_naive_now(self):
        self.assertEqual(codes("def f():\n    return datetime.now()\n"), ["DJ008"])
        self.assertEqual(codes("def f():\n    return datetime.utcnow()\n"), ["DJ008"])
        self.assertEqual(codes("def f():\n    return datetime.now(timezone.utc)\n"), [])
        self.assertEqual(codes("def f():\n    return timezone.now()\n"), [])

    def test_print(self):
        self.assertEqual(codes("def f():\n    print('x')\n"), ["DJ009"])
        self.assertEqual(codes("def f():\n    print('x')\n", "app/tests.py"), [])

    def test_eval_exec_pickle(self):
        for src in ("eval(x)\n", "exec(x)\n", "pickle.loads(data)\n"):
            self.assertEqual(codes(src), ["DJ011"])

    def test_random_for_tokens(self):
        self.assertEqual(codes("def make_token():\n    return random.randint(0, 999999)\n"), ["DJ010"])
        self.assertEqual(codes("def shuffle_demo():\n    return random.choice([1, 2])\n"), [])
        self.assertEqual(codes("def make_token():\n    return secrets.token_hex(16)\n"), [])


class NetworkAndSecretTests(unittest.TestCase):
    def test_requests_without_timeout(self):
        self.assertEqual(codes("def f():\n    requests.get('https://x')\n"), ["DJ012"])
        self.assertEqual(codes("def f():\n    requests.post('https://x', json={}, timeout=5)\n"), [])

    def test_shell_true_and_verify_false(self):
        self.assertEqual(codes("def f(c):\n    subprocess.run(c, shell=True)\n"), ["DJ027"])
        self.assertEqual(codes("def f():\n    requests.get('https://x', timeout=3, verify=False)\n"), ["DJ028"])

    def test_hardcoded_secret(self):
        self.assertEqual(codes("PAYSTACK_SECRET_KEY = 'sk_live_abcdef123456'\n"), ["DJ013"])
        self.assertEqual(codes("password = 'hunter2hunter2'\n"), ["DJ013"])
        self.assertEqual(codes("PAYSTACK_SECRET_KEY = os.environ['PAYSTACK_SECRET_KEY']\n"), [])
        self.assertEqual(codes("password = 'short'\n"), [])
        self.assertEqual(codes("password = 'hunter2hunter2'\n", "app/tests/test_login.py"), [])

    def test_settings_checks(self):
        self.assertEqual(codes("DEBUG = True\n", "config/settings.py"), ["DJ017"])
        self.assertEqual(codes("DEBUG = True\n", "config/settings_dev.py"), [])
        self.assertEqual(codes("ALLOWED_HOSTS = ['*']\n", "config/settings.py"), ["DJ018"])
        self.assertEqual(codes("ALLOWED_HOSTS = ['api.example.com']\n", "config/settings.py"), [])

    def test_float_money(self):
        self.assertEqual(codes("class P(models.Model):\n    price = models.FloatField()\n", "app/models.py"), ["DJ014"])
        self.assertEqual(codes("class P(models.Model):\n    price_minor = models.BigIntegerField()\n", "app/models.py"), [])
        self.assertEqual(codes("class P(models.Model):\n    temperature = models.FloatField()\n", "app/models.py"), [])


class DataAccessTests(unittest.TestCase):
    def test_query_in_loop(self):
        src = "def f(convs):\n    for c in convs:\n        m = Message.objects.filter(conversation=c).last()\n"
        self.assertEqual(codes(src, "app/services.py"), ["DJ024"])

    def test_no_loop_no_flag(self):
        self.assertEqual(codes("def f(c):\n    return Message.objects.filter(conversation=c)\n", "app/selectors.py"), [])

    def test_multiple_writes_without_atomic(self):
        src = "def f(a, b):\n    a.save()\n    b.save()\n"
        self.assertEqual(codes(src, "app/services.py"), ["DJ020"])

    def test_atomic_silences(self):
        src = "def f(a, b):\n    with transaction.atomic():\n        a.save()\n        b.save()\n"
        self.assertEqual(codes(src, "app/services.py"), [])
        src2 = "@transaction.atomic\ndef f(a, b):\n    a.save()\n    b.save()\n"
        self.assertEqual(codes(src2, "app/services.py"), [])

    def test_single_write_is_fine(self):
        self.assertEqual(codes("def f(a):\n    a.save()\n", "app/services.py"), [])


class MiscTests(unittest.TestCase):
    def test_csrf_exempt_is_info(self):
        src = "@csrf_exempt\ndef webhook(request):\n    return 1\n"
        self.assertEqual([(f.level, f.code) for f in dr.review_source(src, "app/views.py")], [("info", "DJ004")])

    def test_syntax_error_reported(self):
        self.assertEqual(codes("def f(:\n"), ["DJ000"])

    def test_findings_sorted_and_deduplicated(self):
        src = "def f(a=[]):\n    print(1)\n    print(2)\n"
        lines = [f.line for f in dr.review_source(src)]
        self.assertEqual(lines, sorted(lines))

    def test_review_path_and_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "good.py").write_text("def f():\n    return 1\n")
            (root / "bad.py").write_text("def f(a=[]):\n    pass\n")
            (root / "migrations").mkdir()
            (root / "migrations" / "0001.py").write_text("def f(a=[]):\n    pass\n")
            result = dr.review_path(root)
            self.assertEqual([Path(p).name for p in result], ["bad.py"])
            self.assertEqual(dr.main([str(root)]), 1)
            (root / "bad.py").write_text("def f(a=None):\n    pass\n")
            self.assertEqual(dr.main([str(root)]), 0)


if __name__ == "__main__":
    unittest.main()
