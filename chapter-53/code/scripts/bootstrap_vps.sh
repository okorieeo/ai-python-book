#!/usr/bin/env bash
# bootstrap_vps.sh - first-day setup for a fresh Ubuntu VPS (Chapter 53).
#
# Run ONCE, as root, on the new server. Safe to run again: every step checks before it changes anything.
#
#   sudo ./bootstrap_vps.sh --user deploy --pubkey-file ./laptop.pub --harden-ssh
#   ./bootstrap_vps.sh --dry-run --user deploy --pubkey-file ./laptop.pub --harden-ssh   # preview, changes nothing
#
# Options:
#   --user NAME          the administrator account to create (default: deploy)
#   --pubkey-file FILE   your PUBLIC key (the .pub file). Required.
#   --harden-ssh         turn off password and root login (only if the new user's key is installed)
#   --swap-gb N          create an N GB swap file if the server has none (default: 2, 0 = skip)
#   --timezone ZONE      default: UTC
#   --close-3000         do NOT open port 3000 (use when you will not install Dokploy yet)
#   --dry-run            print what would happen, change nothing
set -euo pipefail

USER_NAME="deploy"; PUBKEY_FILE=""; HARDEN_SSH=0; SWAP_GB=2; TZ_NAME="UTC"; OPEN_3000=1; DRY=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HERE/../config"

say()  { printf '\n==> %s\n' "$*"; }
run()  { if [ "$DRY" = 1 ]; then printf '[dry-run]'; printf ' %q' "$@"; printf '\n'; else "$@"; fi; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --user)        USER_NAME="${2:?--user needs a value}"; shift 2 ;;
    --pubkey-file) PUBKEY_FILE="${2:?--pubkey-file needs a value}"; shift 2 ;;
    --harden-ssh)  HARDEN_SSH=1; shift ;;
    --swap-gb)     SWAP_GB="${2:?--swap-gb needs a value}"; shift 2 ;;
    --timezone)    TZ_NAME="${2:?--timezone needs a value}"; shift 2 ;;
    --close-3000)  OPEN_3000=0; shift ;;
    --dry-run)     DRY=1; shift ;;
    -h|--help)     sed -n '2,15p' "$0"; exit 0 ;;
    *)             die "unknown option: $1" ;;
  esac
done

[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "invalid user name: $USER_NAME"
[[ "$SWAP_GB" =~ ^[0-9]+$ ]] || die "--swap-gb must be a whole number"
[ -n "$PUBKEY_FILE" ] || die "--pubkey-file is required (the PUBLIC key, ending in .pub)"
[ -r "$PUBKEY_FILE" ] || die "cannot read $PUBKEY_FILE"
if grep -q 'PRIVATE KEY' "$PUBKEY_FILE"; then die "that file contains a PRIVATE key. Never copy a private key to a server."; fi
grep -Eq '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+|sk-ssh-ed25519@openssh.com) ' "$PUBKEY_FILE" \
  || die "$PUBKEY_FILE does not look like a public key (it must start with ssh-ed25519 or similar)"
if [ "$DRY" = 0 ]; then
  [ "$(id -u)" = 0 ] || die "run as root (sudo ./bootstrap_vps.sh ...)"
  # shellcheck disable=SC1091
  . /etc/os-release; [ "${ID:-}" = ubuntu ] || die "this script is for Ubuntu (found: ${ID:-unknown})"
fi

say "1/8 Update packages and install tools"
run apt-get update
run env DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
run env DEBIAN_FRONTEND=noninteractive apt-get -y install ufw fail2ban unattended-upgrades curl ca-certificates

say "2/8 Timezone"
run timedatectl set-timezone "$TZ_NAME"

say "3/8 Administrator account '$USER_NAME'"
if [ "$DRY" = 1 ] || ! id "$USER_NAME" >/dev/null 2>&1; then
  run adduser --disabled-password --gecos "" "$USER_NAME"
  echo "Set a password for $USER_NAME (needed for sudo):"
  run passwd "$USER_NAME"
fi
run usermod -aG sudo "$USER_NAME"
run install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "/home/$USER_NAME/.ssh"
if [ "$DRY" = 1 ]; then
  printf '[dry-run] append %s to /home/%s/.ssh/authorized_keys (if not already there)\n' "$PUBKEY_FILE" "$USER_NAME"
else
  AK="/home/$USER_NAME/.ssh/authorized_keys"; touch "$AK"
  grep -qxFf "$PUBKEY_FILE" "$AK" || cat "$PUBKEY_FILE" >> "$AK"
  chown "$USER_NAME:$USER_NAME" "$AK"; chmod 600 "$AK"
fi

say "4/8 Firewall (UFW): deny incoming, allow SSH, HTTP, HTTPS"
run ufw default deny incoming
run ufw default allow outgoing
run ufw limit 22/tcp
run ufw allow 80/tcp
run ufw allow 443/tcp
if [ "$OPEN_3000" = 1 ]; then run ufw allow 3000/tcp; fi
run ufw --force enable

say "5/8 SSH hardening"
if [ "$HARDEN_SSH" = 1 ]; then
  run install -m 644 "$CONFIG_DIR/00-hardening.conf" /etc/ssh/sshd_config.d/00-hardening.conf
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] sshd -t   (validate the configuration; remove the file again if it fails)"
    echo "[dry-run] systemctl reload ssh"
  else
    sshd -t || { rm -f /etc/ssh/sshd_config.d/00-hardening.conf; die "sshd rejected the configuration; the hardening file was removed"; }
    systemctl reload ssh || systemctl restart ssh
  fi
  echo "KEEP THIS SESSION OPEN. In a NEW terminal run:  ssh $USER_NAME@<server-ip>   and confirm it works."
else
  echo "skipped (pass --harden-ssh once you know the key login works)"
fi

say "6/8 fail2ban"
run install -m 644 "$CONFIG_DIR/jail.local" /etc/fail2ban/jail.local
run systemctl enable --now fail2ban
run systemctl restart fail2ban

say "7/8 Automatic security updates"
run install -m 644 "$CONFIG_DIR/20auto-upgrades" /etc/apt/apt.conf.d/20auto-upgrades
run install -m 644 "$CONFIG_DIR/52unattended-upgrades-local" /etc/apt/apt.conf.d/52unattended-upgrades-local

say "8/8 Swap file (${SWAP_GB} GB)"
if [ "$SWAP_GB" -gt 0 ] && { [ "$DRY" = 1 ] || [ -z "$(swapon --show --noheadings)" ]; }; then
  run fallocate -l "${SWAP_GB}G" /swapfile
  run chmod 600 /swapfile
  run mkswap /swapfile
  run swapon /swapfile
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] add '/swapfile none swap sw 0 0' to /etc/fstab and set vm.swappiness=10"
  else
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf; sysctl -q --system
  fi
else
  echo "skipped (swap already present, or --swap-gb 0)"
fi

say "Done. Next: verify with  sudo python3 -m vpscheck.audit"
