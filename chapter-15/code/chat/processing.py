"""A stand-in for real document processing (real parsing arrives in Part VI).

Filenames choose the behaviour so you can practise every failure mode:
    report.pdf   works
    flaky.pdf    fails twice with a temporary error, then works
    timeout.pdf  always fails with a temporary error
    corrupt.pdf  fails with a permanent error
"""
import time

from django.conf import settings

class TransientError(Exception):
    """Might work if we try again: a timeout, a busy service."""

class PermanentError(Exception):
    """Will never work: a corrupt or unsupported file."""

def extract_chunks(document, attempt):
    time.sleep(getattr(settings, "FAKE_PROCESSING_SECONDS", 1))
    name = document.filename
    if name.startswith("corrupt"):
        raise PermanentError("The file could not be read.")
    if name.startswith("timeout") or (name.startswith("flaky") and attempt < 2):
        raise TransientError("Storage did not answer in time.")
    return [f"{name} chunk {n}" for n in range(1, 4)]
