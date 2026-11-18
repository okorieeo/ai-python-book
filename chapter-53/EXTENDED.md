# Chapter 53 — Preparing an Ubuntu VPS: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Choosing a Provider and Server Size › Which Ubuntu version?

Use an **LTS** (long-term support) release, because it gets five years of security updates. Two are relevant right now. **Ubuntu 24.04 LTS** is supported until 2029. **Ubuntu 26.04 LTS** (released on 23 April 2026, with its first point release in August) is supported until April 2031, and ships newer components, including a Rust rewrite of sudo called sudo-rs. Every command in this chapter works on both, and the places where they differ are marked.

> **Check before you pick 26.04**
>
> Dokploy’s installation guidance lists the Ubuntu versions it supports and tests against. Because 26.04 is recent, look at Dokploy’s installation page (and its release notes) before you create the server, and choose the newest LTS that it lists. If you are unsure, Ubuntu 24.04 LTS is the conservative choice and still has years of support. Do not use a non-LTS release such as 25.10 for a server: its support ends after a few months.


## Choosing a Provider and Server Size › Before you click Create

> **Ordering checklist**
>
> - **Region:** the one closest to most of your users.
> - **Image:** plain Ubuntu LTS. Do not pick a "one-click app" or marketplace image: Dokploy installs Docker itself and expects a clean server.
> - **Size:** from the table above, with enough disk.
> - **SSH key:** add your public key in the order form (you will make one in 53.3). Without it, some providers email you a root password, which is exactly what we are avoiding.
> - **Backups:** switch on the provider’s scheduled backups, and note how many copies it keeps.
> - **Networking:** a public IPv4 address. Add IPv6 if offered and you are comfortable with it.
> - **Name:** a clear hostname such as chat-prod-1.


## SSH Keys: The Front Door › Generate a key

Use the **ed25519** type: it is modern, short and fast. Run this on your laptop, not on the server. It works the same in macOS Terminal, Linux, and Windows PowerShell (Windows 10 and 11 include the OpenSSH client).

**bash terminal (your laptop)**

```bash
ssh-keygen -t ed25519 -C "you@laptop-2026" -f ~/.ssh/id_ed25519_vps
```

You will be asked for a **passphrase**. Set one. The passphrase encrypts the private key on your disk, so a stolen laptop or backup does not mean a stolen server. The command creates two files:

| **File** | **What it is** | **Who may see it** |
|---|---|---|
| id_ed25519_vps | The **private** key | Only you. Never email it, paste it into a chat, commit it or copy it to a server |
| id_ed25519_vps.pub | The **public** key (one line starting with ssh-ed25519) | Anyone. This is the one you give to the provider and the server |

**bash terminal**

```bash
cat ~/.ssh/id_ed25519_vps.pub
```

**text example output (yours will differ)**

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... you@laptop-2026
```

Copy that whole line into the provider’s "SSH keys" form when you create the server. On Windows PowerShell the file is at $env:USERPROFILE\.ssh\id_ed25519_vps.pub, and you can print it with type.

> **Treat the private key like a password manager vault**
>
> If the private key leaks, anyone can log in as you until you remove its public half from the server. Use one key per device so that a lost laptop is a one-line fix, back it up in your password manager or an encrypted drive, and never put it in a Git repository (section 17.9). SSH refuses to use a private key that other users on your computer can read, so keep its permissions at 600 on macOS and Linux.


## SSH Keys: The Front Door › Give the server a short name

An entry in ~/.ssh/config saves you from typing the address and key every time, and it makes the commands in this chapter shorter. We use 203.0.113.10, an address reserved for documentation, as the server’s IP. Replace it with yours. For now the user is root, because a new server only has that account. We change it in 53.5.

**text ~/.ssh/config**

```text
Host vps
    HostName 203.0.113.10
    User root
    IdentityFile ~/.ssh/id_ed25519_vps
    IdentitiesOnly yes
    ServerAliveInterval 60
```

`IdentitiesOnly yes` makes SSH offer only this key instead of trying every key in your agent, which avoids being refused for "too many authentication failures". `ServerAliveInterval` sends a small message every minute so idle connections are not dropped by routers.


## The Firewall: UFW, the Cloud Firewall and Docker › UFW, the Uncomplicated Firewall

Ubuntu includes **UFW**, a friendly front end for the Linux firewall. It is installed but switched off on a new server. The order of the commands below matters: **allow SSH before you enable the firewall**, or you cut off your own connection.

**bash terminal (on the server, as deploy)**

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw limit 22/tcp comment 'SSH, rate limited'
sudo ufw allow 80/tcp comment 'HTTP (Traefik)'
sudo ufw allow 443/tcp comment 'HTTPS (Traefik)'
sudo ufw allow 3000/tcp comment 'Dokploy panel (temporary)'
sudo ufw enable
```

UFW warns that the command "may disrupt existing ssh connections". Because you allowed port 22 first, answer y. **limit** is allow plus protection: UFW temporarily refuses an address that opens six or more connections to that port within 30 seconds. Check the result:

**bash terminal**

```bash
sudo ufw status verbose
```

**text example output**

```text
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
22/tcp                     LIMIT IN    Anywhere                   # SSH, rate limited
80/tcp                     ALLOW IN    Anywhere                   # HTTP (Traefik)
443/tcp                    ALLOW IN    Anywhere                   # HTTPS (Traefik)
3000/tcp                   ALLOW IN    Anywhere                   # Dokploy panel (temporary)
22/tcp (v6)                LIMIT IN    Anywhere (v6)              # SSH, rate limited
...
```

The "(v6)" lines are the same rules for IPv6, which UFW handles automatically when IPV6=yes in /etc/default/ufw (the default). To remove a rule later, use sudo ufw delete allow 3000/tcp. Immediately open a new terminal and confirm you can still ssh in.

> **If you lock yourself out**
>
> Every provider has a **web console** (sometimes called "Console", "VNC" or "Recovery") that gives you a terminal without SSH. Log in there as root or deploy, run sudo ufw allow 22/tcp (or sudo ufw disable), and try again. Know where this button is before you need it.


## Hardening SSH and Stopping Brute Force › Trap 1: which file wins

SSH reads /etc/ssh/sshd_config and then every file in /etc/ssh/sshd_config.d/. For each setting the **first value it reads wins**. Cloud images often include a file there, such as 50-cloud-init.conf, that sets PasswordAuthentication yes. If you add PasswordAuthentication no to sshd_config, the cloud file may silently beat it, and you will believe you are protected when you are not.

Our solution has two parts: put our settings in a file named 00-hardening.conf, so it is read first, and **ask SSH what it is really doing** instead of trusting the files.

**bash terminal (on the server)**

```bash
ls -la /etc/ssh/sshd_config.d/
sudo grep -rEi 'passwordauthentication|permitrootlogin|kbdinteractive' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/
```

**text /etc/ssh/sshd_config.d/00-hardening.conf**

```text
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
```

| **Setting** | **What it does** |
|---|---|
| PubkeyAuthentication yes | Keys are the way in |
| PasswordAuthentication no | Passwords are never accepted over SSH |
| KbdInteractiveAuthentication no | Closes the "keyboard-interactive" path, which can bring passwords back |
| PermitRootLogin no | Nobody logs in as root; you use deploy and sudo |
| MaxAuthTries 3 | Three attempts per connection |
| LoginGraceTime 30 | Half a minute to finish logging in |
| X11Forwarding no | No graphical forwarding you do not use |
| ClientAliveInterval and CountMax | Disconnect dead sessions after about 10 minutes |

Create the file, check it for mistakes and see the effective result:

**bash terminal**

```bash
sudoedit /etc/ssh/sshd_config.d/00-hardening.conf    # paste the settings above
sudo sshd -t                                          # prints nothing if the syntax is valid
sudo sshd -T | grep -E '^(passwordauthentication|permitrootlogin|pubkeyauthentication|kbdinteractiveauthentication|maxauthtries) '
```

**text expected output**

```text
permitrootlogin no
pubkeyauthentication yes
passwordauthentication no
kbdinteractiveauthentication no
maxauthtries 3
```

If any line differs, another file is overriding yours: find it with the grep command above and remove or edit it. When the output is right, apply it. **Keep your current session open.**

**bash terminal**

```bash
sudo systemctl reload ssh || sudo systemctl restart ssh
```

Restarting SSH does not drop connections that are already open, which is what makes this safe. Now open a **new** terminal and prove two things: key login still works, and a password attempt is refused.

**bash terminal (a new window on your laptop)**

```bash
ssh deploy@203.0.113.10                       # should log in with your key
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password deploy@203.0.113.10
```

**text expected output of the second command**

```text
deploy@203.0.113.10: Permission denied (publickey).
```

> **An optional safety net: an automatic undo**
>
> If you are nervous, schedule the change to undo itself in ten minutes, then cancel the undo once you have confirmed everything works:
>
> `sudo systemd-run --on-active=10min --unit=ssh-rollback /bin/sh -c "rm -f /etc/ssh/sshd_config.d/00-hardening.conf; systemctl reload ssh"`
>
> and, after the tests pass: `sudo systemctl stop ssh-rollback.timer`.


## Hardening SSH and Stopping Brute Force › fail2ban: quiet the noise

With key-only login, password guessing cannot succeed, but bots still try, filling your logs and costing CPU. **fail2ban** watches the SSH log and bans an address for a while after repeated failures.

**bash terminal**

```bash
sudo apt install -y fail2ban
sudoedit /etc/fail2ban/jail.local
```

**text /etc/fail2ban/jail.local**

```text
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd
# ignoreip = 127.0.0.1/8 ::1 203.0.113.50

[sshd]
enabled = true
port    = ssh
```

**bash terminal**

```bash
sudo systemctl enable --now fail2ban
sudo systemctl restart fail2ban
sudo fail2ban-client status sshd
```

The status shows how many failures and bans it has seen. If you ever ban yourself (typing a wrong passphrase repeatedly is enough), unban with sudo fail2ban-client set sshd unbanip YOUR.IP.ADDRESS, and consider listing your fixed address in ignoreip. fail2ban protects SSH only. Protecting your web endpoints from abuse is the job of the rate limits from section 17.8.


## Automatic Updates, Swap and Housekeeping › A swap file: a safety net, not a speed-up

When a server runs out of memory, Linux kills a process, and during a deploy that is often the Next.js build ("Killed", or exit code 137). **Swap** is disk space used as slow emergency memory. It will not make a too-small server fast, but it turns a crash into a slowdown. On a 2 to 4 GB server, add a 2 GB swap file:

**bash terminal**

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
swapon --show && free -h
```

swappiness=10 tells Linux to prefer real memory and use swap only when it must. If your server uses swap all the time, you need a bigger plan.


## Domain Names and DNS › Our plan: one server, three names

Our single VPS serves several hostnames, and Traefik will tell them apart by name (the picture below). All three point at the same address, and each gets its own certificate later.

*(figure: see the printed book)*

| **Name** | **Record** | **Points to** | **Serves** |
|---|---|---|---|
| app.example.com | A | 203.0.113.10 | The Next.js web app |
| api.example.com | A | 203.0.113.10 | The Django API and WebSockets |
| deploy.example.com | A | 203.0.113.10 | The Dokploy panel |
| example.com (the "apex") | A | 203.0.113.10 | Optional: redirect to app |
| www.example.com | CNAME | example.com | Optional: redirect to the apex |

Separate names for the web app and the API keep CORS and cookies explicit (section 17.4) and let you move them to different servers later without changing the code. Use **example.com** only as a placeholder: replace it with your own domain everywhere.

> **Wildcards for later**
>
> A wildcard record such as *.example.com → 203.0.113.10 sends every subdomain to your server. It is handy for per-branch preview environments, but it also means a typo resolves instead of failing. Start with explicit records and add a wildcard only when you need one. Note that certificates for wildcard names need the DNS-based validation described in 53.10.


## Domain Names and DNS › Look it up yourself

**bash terminal (your laptop)**

```bash
dig +short A app.example.com                 # your system's resolver
dig +short A app.example.com @1.1.1.1        # a public resolver, to compare
dig +short NS example.com                    # who is authoritative
nslookup app.example.com                     # same idea, works on Windows too
```

**text expected output**

```text
203.0.113.10
```

The most common DNS mistake is typing the full name into a form that adds the domain for you, producing app.example.com.example.com. Enter just app. The second is forgetting the record for one name. The check script in Chapter 53 tests all of them at once.


## HTTPS and Certificates › Certificates are getting shorter, so automation matters

Let’s Encrypt certificates are valid for **90 days** today, and the industry is moving to shorter lifetimes: Let’s Encrypt has announced that it will reduce the maximum to **45 days by 2028**, and the browser industry’s rules will cap all public certificates at 47 days from March 2029. Two lessons follow. First, never plan to renew certificates by hand. Second, Let’s Encrypt **stopped sending expiry reminder emails** in 2025, so if automatic renewal breaks, nobody tells you. You must watch certificates yourself, and Chapter 53 gives you a script for that. A good rule: alert when less than a quarter of a certificate’s lifetime is left, because healthy renewal happens with about a third left.

> **Do not burn through issuance limits**
>
> Let’s Encrypt limits how often you can request certificates for the same names. If you keep deleting and re-creating the certificate storage while experimenting, you can lock yourself out for days. Fix the cause (usually DNS or a closed port) instead of retrying in a loop, and avoid wiping Traefik’s certificate volume.


## HTTPS and Certificates › Checking a certificate

**bash terminal (your laptop)**

```bash
curl -sI https://app.example.com | head -1
openssl s_client -connect app.example.com:443 -servername app.example.com </dev/null 2>/dev/null | openssl x509 -noout -issuer -dates
```

**text example output**

```text
HTTP/2 200
issuer=C = US, O = Let's Encrypt, CN = R...
notBefore=...
notAfter=...
```

Your browser’s padlock shows the same information, and an online tester such as SSL Labs gives a detailed report for public sites. For your own monitoring, 53.11 has a script.


## Verifying the Server

A setting you believe is on, but is not, is worse than one you know is off. So we finish with a check that reads the **real** state of the server instead of your memory of it. The chapter’s code includes a small Python package called vpscheck that uses only the standard library. It has four jobs, and each reads real output from the system:

| **Check** | **Reads** | **Catches** |
|---|---|---|
| SSH | sudo sshd -T (the effective settings) | Password login still on, root login allowed, cloud-init overrides |
| Firewall | sudo ufw status verbose | UFW off, default allow, databases opened, forgotten ports |
| Listening ports | sudo ss -H -tulpn | PostgreSQL or Redis listening on a public address |
| Updates | /etc/apt/apt.conf.d/20auto-upgrades and /var/run/reboot-required | Automatic updates off, a pending reboot |

Plus two checks that look from the outside in: **DNS** (do the names point at this server?) and **TLS** (when does each certificate end?). Copy the folder to your server and run it:

**bash terminal (your laptop)**

```bash
scp -r chapter_53_code vps:~
```

**bash terminal (on the server)**

```bash
cd ~/chapter_53_code
sudo python3 -m vpscheck.audit
python3 -m vpscheck.audit --dns app.example.com api.example.com deploy.example.com --ip 203.0.113.10
python3 -m vpscheck.audit --certs app.example.com api.example.com     # after Chapter 54
```

The exit code is 1 when any check fails, so you can run the script from a scheduled job or CI. Here is what it prints for a healthy server, then for a server with the classic first-day mistakes. This output is real, produced from the sample command output stored in tests/fixtures:

**text verified output: a prepared server**

```text
[PASS] ssh passwordauthentication: no
[PASS] ssh kbdinteractiveauthentication: no
[PASS] ssh pubkeyauthentication: yes
[PASS] ssh permitemptypasswords: no
[PASS] ssh permitrootlogin: no
[PASS] ssh maxauthtries: 3
[PASS] ufw active: enabled
[PASS] ufw default incoming: deny
[PASS] ufw ssh rule: port 22 is allowed
[WARN] ufw port 3000: Dokploy panel port: close it once the panel has a domain with HTTPS (Chapter 54)
[PASS] listening 22: sshd
[PASS] listening 80: docker-proxy
[PASS] listening 443: docker-proxy
[PASS] listening 3000: docker-proxy
[PASS] automatic updates: package lists and unattended upgrades are on
[PASS] reboot: no reboot pending

15 passed, 1 warnings, 0 failures
```

**text verified output: a server with first-day mistakes**

```text
[FAIL] ssh passwordauthentication: is 'yes', want 'no': anyone can guess passwords
[FAIL] ssh permitrootlogin: is 'yes', root must not log in with a password
[WARN] ssh maxauthtries: 6 attempts per connection; 3 or 4 is plenty
[FAIL] ufw default incoming: is 'allow', want 'deny'
[FAIL] ufw port 5432: PostgreSQL is open to the internet
[WARN] ufw port 8080: not in the expected list (22, 80, 443): is it needed?
[FAIL] listening 5432: PostgreSQL (docker-proxy) listens on a public address: bind it to 127.0.0.1 or keep it on a private Docker network
[FAIL] listening 6379: Redis (docker-proxy) listens on a public address: bind it to 127.0.0.1 or keep it on a private Docker network
[FAIL] automatic updates: turn on APT::Periodic::Update-Package-Lists and Unattended-Upgrade
[WARN] reboot: /var/run/reboot-required exists: schedule a reboot (a new kernel or library is waiting)

6 passed, 3 warnings, 7 failures
```

(The second listing omits its passing lines for space.) The script cannot see Docker’s firewall rules, which is exactly the Docker catch from 53.6, so also look from **outside**. From your laptop, not the server, test the doors that must be closed:

**bash terminal (your laptop)**

```bash
nc -vz 203.0.113.10 5432          # PostgreSQL: expect a refusal or a timeout
nc -vz 203.0.113.10 6379          # Redis: expect a refusal or a timeout
nc -vz 203.0.113.10 22            # SSH: expect "succeeded"
# Windows PowerShell:  Test-NetConnection 203.0.113.10 -Port 5432
# More thorough, if installed:   nmap -Pn -p 1-10000 203.0.113.10
```

Only scan servers you own. Scanning other people’s machines can be treated as an attack.


## Using AI Assistants for Server Work

An AI assistant is a good tutor for server administration: it explains an unfamiliar line, compares two options, drafts a script and notices the typo you stared past. It is also a confident source of commands that lock you out of your own server. Server work has a property that most coding does not: **a wrong command can be hard to undo**. So the rules from Chapter 50 apply with extra force.

- **Ask for an explanation before a command.** "Explain each line of this sshd config, and tell me which line could lock me out if the key login is not working yet."
- **Never paste secrets.** Private keys, .env files, database passwords, API tokens and provider credentials stay out of any chat. Public keys, hostnames and sanitized command output are fine.
- **Check current facts.** Ubuntu releases, Docker, Dokploy and certificate rules change. Ask the assistant for the official documentation link and read it for anything that affects security.
- **Test in a safe place.** Try a risky change on a throwaway server first (it costs cents per hour), or take a snapshot before you start.
- **Keep the second window.** The "test in a second terminal before closing the first" habit applies no matter who wrote the command.
- **If you let Claude Code work on a server,** read Chapter 50 first: give it a non-root account, keep secrets out of reach, and review every command that changes the firewall, SSH or users.
A prompt that works well for a review:

**text prompt template**

```text
I am preparing an Ubuntu 24.04 LTS server for Dokploy. Here is the output of
`sudo sshd -T | grep -E "^(passwordauth|permitroot|pubkey|kbdinteractive)"`
and `sudo ufw status verbose` (no secrets included).
List anything that is not production-safe, ordered by risk, and for each item
give the exact command to fix it AND the command to verify the fix.
Warn me about anything that could lock me out.
```
