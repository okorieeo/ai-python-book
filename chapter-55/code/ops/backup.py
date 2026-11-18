#!/usr/bin/env python3
"""Back up PostgreSQL: dump, check, encrypt, copy offsite, prune, and tell an outside monitor.

Run from the host (not inside a container), on a schedule:   python3 ops/backup.py
Settings come from the environment (keep them in a root-only file, never in Git):
    BACKUP_AGE_RECIPIENT   age public key (age1...). Required before any offsite copy.
    BACKUP_RCLONE_REMOTE   e.g. b2:my-bucket/ai-chat   (optional; any rclone remote)
    BACKUP_HEARTBEAT_URL   Healthchecks.io-style URL   (optional but strongly advised)
Standard library only. Every external command is built by a small function so it is testable.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.observability.heartbeat import heartbeat  # noqa: E402
import retention  # noqa: E402


class BackupError(RuntimeError):
    """A step failed; the message says which, and never contains secrets."""


@dataclass
class Config:
    compose_dir: Path
    backup_dir: Path
    service: str = "db"
    prefix: str = "chat"
    age_recipient: str | None = None
    rclone_remote: str | None = None
    heartbeat_url: str | None = None
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6
    min_bytes: int = 1024


def build_dump_command(service: str) -> list[str]:
    # sh -c so the CONTAINER's own POSTGRES_USER / POSTGRES_DB are used; -T = no terminal
    return ["docker", "compose", "exec", "-T", service, "sh", "-c", 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"']


def build_verify_command(service: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", service, "pg_restore", "--list"]


def build_encrypt_command(recipient: str, source: Path, target: Path) -> list[str]:
    return ["age", "-r", recipient, "-o", str(target), str(source)]


def build_upload_command(remote: str, path: Path) -> list[str]:
    return ["rclone", "copyto", str(path), f"{remote.rstrip('/')}/{path.name}"]


def default_runner(cmd, *, cwd=None, stdin: Path | None = None, stdout: Path | None = None) -> int:
    fin = open(stdin, "rb") if stdin else None
    fout = open(stdout, "wb") if stdout else None
    try:
        return subprocess.run(cmd, cwd=cwd, stdin=fin, stdout=fout).returncode
    except FileNotFoundError:
        return 127
    finally:
        for handle in (fin, fout):
            if handle:
                handle.close()


def run_backup(cfg: Config, run=default_runner, now=datetime.now,
               heartbeat_fn=heartbeat) -> Path:
    if cfg.rclone_remote and not cfg.age_recipient:
        raise BackupError("refusing to copy an unencrypted dump offsite: "
                          "set BACKUP_AGE_RECIPIENT")
    with heartbeat_fn(cfg.heartbeat_url):
        cfg.backup_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(cfg.backup_dir, 0o700)
        stamp = now().strftime("%Y%m%d-%H%M%S")
        plain = cfg.backup_dir / f"{cfg.prefix}-{stamp}.dump"
        listing = cfg.backup_dir / f".{stamp}.list"
        final: Path | None = None
        succeeded = False
        try:
            if run(build_dump_command(cfg.service), cwd=cfg.compose_dir, stdout=plain) != 0:
                raise BackupError("pg_dump failed")
            os.chmod(plain, 0o600)
            if plain.stat().st_size < cfg.min_bytes:
                raise BackupError("dump is suspiciously small")
            rc = run(build_verify_command(cfg.service), cwd=cfg.compose_dir,
                     stdin=plain, stdout=listing)
            if rc != 0 or "TABLE DATA" not in listing.read_text(errors="replace"):
                raise BackupError("dump does not look restorable "
                                  "(pg_restore --list found no table data)")
            final = plain
            if cfg.age_recipient:
                encrypted = plain.with_name(plain.name + ".age")
                if run(build_encrypt_command(cfg.age_recipient, plain, encrypted)) != 0:
                    raise BackupError("encryption failed")
                os.chmod(encrypted, 0o600)
                final = encrypted
            if cfg.rclone_remote:
                if run(build_upload_command(cfg.rclone_remote, final)) != 0:
                    raise BackupError("offsite copy failed")
            succeeded = True
        finally:
            listing.unlink(missing_ok=True)
            # Keep the plain dump only when it IS the finished local-only backup. After
            # any failure, or once an encrypted copy exists, never leave a plain file.
            if plain.exists() and not (succeeded and final == plain):
                plain.unlink()
        names = [p.name for p in cfg.backup_dir.iterdir() if p.is_file()]
        _, delete = retention.plan_prune(
            names, now().date(), cfg.keep_daily, cfg.keep_weekly, cfg.keep_monthly
        )
        for name in delete:
            (cfg.backup_dir / name).unlink()
        return final


def main(argv=None, environ=os.environ, run=default_runner) -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL backup")
    parser.add_argument("--compose-dir", default=".", type=Path)
    parser.add_argument("--backup-dir", default="backups", type=Path)
    args = parser.parse_args(argv)
    cfg = Config(
        compose_dir=args.compose_dir.resolve(), backup_dir=args.backup_dir.resolve(),
        age_recipient=environ.get("BACKUP_AGE_RECIPIENT") or None,
        rclone_remote=environ.get("BACKUP_RCLONE_REMOTE") or None,
        heartbeat_url=environ.get("BACKUP_HEARTBEAT_URL") or None,
    )
    try:
        path = run_backup(cfg, run=run)
    except BackupError as exc:
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"BACKUP OK: {path.name} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
