import os

MEDIA_LIMITS = {}                       # override any number from
    attachments/limits.py here
SPEECH_API_KEY = os.environ.get("SPEECH_API_KEY", "")
SPEECH_BASE_URL = os.environ.get("SPEECH_BASE_URL") or None     # leave empty for
    the vendor default
TRANSCRIPTION_MODEL = os.environ["TRANSCRIPTION_MODEL"]           # a missing name
    should stop the server at start-up
SPEECH_MODEL = os.environ.get("SPEECH_MODEL", "")
SPEECH_VOICE = os.environ.get("SPEECH_VOICE", "")

# Only the storage behind default_storage must be PRIVATE (Chapter 16): no public
    bucket, no public media URL.
# Celery: use the broker and app you set up in Chapter 15; no new configuration is
    needed.

DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024     # larger files spool to a
    temporary file instead of memory
