# chat-prod-1

- Provider / region / plan: ...
- OS: Ubuntu 24.04 LTS (or 26.04 LTS), created 2026-11-..
- IPv4: 203.0.113.10        IPv6: none
- Admin user: deploy (sudo). Root login and password login disabled.
- SSH: ssh vps (key: id_ed25519_vps, passphrase in the password manager)
- Firewall: UFW + provider firewall; open 22, 80, 443, 3000 (3000 temporary)
- DNS (TTL 300): app, api, deploy -> 203.0.113.10; registrar: ...; 2FA on; auto-renew on
- Backups: provider backups on (copies kept: ..); snapshot chat-prod-1-clean-2026-11
- Updates: unattended security updates on; reboot is manual; Docker updated monthly
- People with access: ...
