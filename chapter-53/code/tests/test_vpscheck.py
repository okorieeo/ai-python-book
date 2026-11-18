import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest

from vpscheck import FAIL, PASS, WARN, worst_status
from vpscheck.audit import collect, main, run_checks
from vpscheck.certcheck import CertInfo, check_cert, evaluate
from vpscheck.dnscheck import check_dns
from vpscheck.ports import check_listeners, parse_ss
from vpscheck.sshd import check_sshd, parse_sshd_t
from vpscheck.ufw import check_ufw, parse_ufw_status
from vpscheck.updates import check_updates, parse_apt_periodic

HERE = os.path.dirname(__file__)
GOOD = os.path.join(HERE, "fixtures", "good")
BAD = os.path.join(HERE, "fixtures", "bad")


def by_name(findings):
    return {f.name: f for f in findings}


class SshdTests(unittest.TestCase):
    def test_parse_keeps_repeated_keys(self):
        parsed = parse_sshd_t("port 22\nlistenaddress 0.0.0.0:22\nlistenaddress [::]:22\n")
        self.assertEqual(parsed["listenaddress"], ["0.0.0.0:22", "[::]:22"])

    def test_hardened_config_passes(self):
        with open(os.path.join(GOOD, "sshd_T.txt")) as fh:
            self.assertEqual(worst_status(check_sshd(parse_sshd_t(fh.read()))), PASS)

    def test_password_login_is_a_failure(self):
        found = by_name(check_sshd(parse_sshd_t("passwordauthentication yes\n")))
        self.assertEqual(found["ssh passwordauthentication"].status, FAIL)

    def test_root_with_key_only_is_a_warning(self):
        found = by_name(check_sshd(parse_sshd_t("permitrootlogin prohibit-password\n")))
        self.assertEqual(found["ssh permitrootlogin"].status, WARN)

    def test_missing_output_is_a_warning_not_a_pass(self):
        found = by_name(check_sshd(parse_sshd_t("")))
        self.assertEqual(found["ssh passwordauthentication"].status, WARN)


class UfwTests(unittest.TestCase):
    def test_parse_active_status(self):
        with open(os.path.join(GOOD, "ufw_status.txt")) as fh:
            status = parse_ufw_status(fh.read())
        self.assertTrue(status.active)
        self.assertEqual(status.default_incoming, "deny")
        self.assertEqual(status.allowed_ports, {22, 80, 443, 3000})

    def test_inactive_firewall_fails(self):
        status = parse_ufw_status("Status: inactive\n")
        self.assertEqual(check_ufw(status)[0].status, FAIL)

    def test_default_allow_and_open_database_fail(self):
        with open(os.path.join(BAD, "ufw_status.txt")) as fh:
            found = by_name(check_ufw(parse_ufw_status(fh.read())))
        self.assertEqual(found["ufw default incoming"].status, FAIL)
        self.assertEqual(found["ufw port 5432"].status, FAIL)
        self.assertEqual(found["ufw port 8080"].status, WARN)

    def test_dokploy_port_is_flagged_as_temporary(self):
        with open(os.path.join(GOOD, "ufw_status.txt")) as fh:
            found = by_name(check_ufw(parse_ufw_status(fh.read())))
        self.assertEqual(found["ufw port 3000"].status, WARN)

    def test_denied_rules_are_not_counted_as_open(self):
        text = "Status: active\nDefault: deny (incoming), allow (outgoing), disabled (routed)\n\n" \
               "To  Action  From\n--  ------  ----\n5432/tcp                   DENY IN     Anywhere\n"
        self.assertEqual(parse_ufw_status(text).allowed_ports, set())


class PortTests(unittest.TestCase):
    def test_parse_and_classify(self):
        with open(os.path.join(GOOD, "ss.txt")) as fh:
            listeners = parse_ss(fh.read())
        public = {l.port for l in listeners if l.is_public and l.proto == "tcp"}
        self.assertEqual(public, {22, 80, 443, 3000})
        resolver = [l for l in listeners if l.port == 53 and l.proto == "udp"][0]
        self.assertEqual(resolver.address, "127.0.0.53")
        self.assertFalse(resolver.is_public)

    def test_public_database_fails(self):
        with open(os.path.join(BAD, "ss.txt")) as fh:
            found = by_name(check_listeners(parse_ss(fh.read())))
        self.assertEqual(found["listening 5432"].status, FAIL)
        self.assertEqual(found["listening 6379"].status, FAIL)

    def test_loopback_database_is_fine(self):
        text = 'tcp LISTEN 0 4096 127.0.0.1:5432 0.0.0.0:* users:(("docker-proxy",pid=9,fd=7))\n' \
               'tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))\n'
        self.assertEqual(worst_status(check_listeners(parse_ss(text))), PASS)


class UpdateTests(unittest.TestCase):
    def test_enabled(self):
        periodic = parse_apt_periodic('APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n')
        self.assertEqual(worst_status(check_updates(periodic, reboot_required=False)), PASS)

    def test_disabled_and_reboot_pending(self):
        periodic = parse_apt_periodic('APT::Periodic::Unattended-Upgrade "0";\n')
        found = by_name(check_updates(periodic, reboot_required=True))
        self.assertEqual(found["automatic updates"].status, FAIL)
        self.assertEqual(found["reboot"].status, WARN)


class DnsTests(unittest.TestCase):
    def test_pass_warn_fail(self):
        table = {"app.example.com": {"203.0.113.10"},
                 "api.example.com": {"203.0.113.10", "198.51.100.7"},
                 "old.example.com": {"198.51.100.7"}}
        found = by_name(check_dns(["app.example.com", "api.example.com", "old.example.com", "nope.example.com"],
                                  "203.0.113.10", resolver=lambda h: table.get(h, set())))
        self.assertEqual(found["dns app.example.com"].status, PASS)
        self.assertEqual(found["dns api.example.com"].status, WARN)
        self.assertEqual(found["dns old.example.com"].status, FAIL)
        self.assertEqual(found["dns nope.example.com"].status, FAIL)


class EvaluateCertTests(unittest.TestCase):
    NOW = 1_800_000_000.0

    def info(self, days_left, lifetime=90):
        return CertInfo("example.com", "Test CA", self.NOW + days_left * 86400 - lifetime * 86400,
                        self.NOW + days_left * 86400, ("example.com",))

    def test_healthy(self):
        self.assertEqual(evaluate(self.info(60), now=self.NOW).status, PASS)

    def test_renewal_looks_stuck_under_a_quarter_of_lifetime(self):
        self.assertEqual(evaluate(self.info(20), now=self.NOW).status, WARN)

    def test_quarter_rule_scales_with_shorter_lifetimes(self):
        # 45-day certificates: 20 days left is healthy (more than a quarter), 10 is not
        self.assertEqual(evaluate(self.info(20, lifetime=45), now=self.NOW).status, PASS)
        self.assertEqual(evaluate(self.info(10, lifetime=45), now=self.NOW).status, WARN)

    def test_emergency_and_expired(self):
        self.assertEqual(evaluate(self.info(3), now=self.NOW).status, FAIL)
        self.assertEqual(evaluate(self.info(-2), now=self.NOW).status, FAIL)


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class LiveTlsTests(unittest.TestCase):
    """Starts a real TLS server on localhost with a throwaway certificate and checks it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.cert, cls.key = os.path.join(cls.tmp, "cert.pem"), os.path.join(cls.tmp, "key.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", cls.key, "-out", cls.cert,
                        "-days", "10", "-subj", "/O=Throwaway Test CA/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, cls.key)
        cls.server = socket.socket()
        cls.server.bind(("127.0.0.1", 0))
        cls.server.listen(5)
        cls.port = cls.server.getsockname()[1]
        cls.running = True

        def serve():
            while cls.running:
                try:
                    conn, _ = cls.server.accept()
                    with context.wrap_socket(conn, server_side=True):
                        pass
                except (OSError, ssl.SSLError):
                    pass

        cls.thread = threading.Thread(target=serve, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.running = False
        cls.server.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_reads_issuer_and_days_left(self):
        finding = check_cert("localhost", self.port, cafile=self.cert)
        self.assertEqual(finding.status, PASS)  # a fresh 10-day certificate: about 10 days left, more than a quarter
        self.assertIn("Throwaway Test CA", finding.detail)
        self.assertRegex(finding.detail, r"\b(9|10) days left")

    def test_untrusted_certificate_fails(self):
        finding = check_cert("localhost", self.port)  # system trust store does not know our throwaway CA
        self.assertEqual(finding.status, FAIL)
        self.assertIn("not trusted", finding.detail)

    def test_closed_port_fails_cleanly(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()
        self.assertEqual(check_cert("localhost", free_port).status, FAIL)


class AuditEndToEndTests(unittest.TestCase):
    def test_good_fixtures_have_no_failures(self):
        self.assertNotEqual(worst_status(run_checks(collect(GOOD))), FAIL)

    def test_bad_fixtures_fail_and_exit_code_is_one(self):
        self.assertEqual(worst_status(run_checks(collect(BAD))), FAIL)
        self.assertEqual(main(["--fixtures", BAD]), 1)
        self.assertEqual(main(["--fixtures", GOOD]), 0)

    def test_empty_command_output_is_not_reported_as_healthy(self):
        empty = {"sshd_T.txt": "", "ufw_status.txt": "", "ss.txt": "", "20auto-upgrades": "", "reboot_required": False}
        statuses = {f.status for f in run_checks(empty)}
        self.assertNotEqual(statuses, {PASS})


if __name__ == "__main__":
    unittest.main()
