#!/usr/bin/env bash
# Install a PINNED actionlint and refuse to run it if the download does not match the checksum published
# with that release. Never pipe a download into a shell: pin the version, check the hash.
set -euo pipefail

VERSION="1.7.12"
SHA256="8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"   # actionlint_1.7.12_linux_amd64.tar.gz
URL="https://github.com/rhysd/actionlint/releases/download/v${VERSION}/actionlint_${VERSION}_linux_amd64.tar.gz"

dest="${1:-$HOME/.local/bin}"
mkdir -p "$dest"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl --fail --silent --show-error --location --max-time 60 --output "$tmp/actionlint.tgz" "$URL"
echo "${SHA256}  $tmp/actionlint.tgz" | sha256sum --check --status || {
  echo "actionlint download does not match the pinned checksum" >&2
  exit 1
}
tar -xzf "$tmp/actionlint.tgz" -C "$tmp" actionlint
install -m 0755 "$tmp/actionlint" "$dest/actionlint"
"$dest/actionlint" -version | head -1
