# Chapter 53 code: Preparing an Ubuntu VPS

```
chapter_53_code/
  scripts/bootstrap_vps.sh      first-day setup (user, UFW, SSH hardening, fail2ban, updates, swap); has --dry-run
  config/                       the files the script installs: 00-hardening.conf, jail.local, 20auto-upgrades, 52unattended-upgrades-local
  vpscheck/                     audit package (standard library only): ssh, ufw, listening ports, updates, DNS, TLS certificates
  tests/                        26 tests + sample command output in tests/fixtures
```

Python 3.10 or newer; no packages to install.

```bash
# run the tests on your laptop (no server needed)
python3 -m unittest discover -s tests -t . -v

# preview the bootstrap script without changing anything
./scripts/bootstrap_vps.sh --dry-run --user deploy --pubkey-file ~/.ssh/id_ed25519.pub --harden-ssh

# audit a real server (run ON the server, with sudo)
sudo python3 -m vpscheck.audit
python3 -m vpscheck.audit --dns app.example.com api.example.com --ip 203.0.113.10
python3 -m vpscheck.audit --certs app.example.com
```

Copy the folder to the server with `scp -r chapter_53_code deploy@SERVER_IP:~`.
Read every script before you run it on a server you care about.
