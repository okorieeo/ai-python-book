# Add to config/settings.py. Everything tunable lives here, none of it in code.
import os

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]            # server only. Never in the mobile app (Chapter 26)

AI_PRIMARY_MODEL = os.environ.get("AI_PRIMARY_MODEL", "claude-sonnet-5-5")
AI_FALLBACK_MODEL = os.environ.get("AI_FALLBACK_MODEL", "claude-haiku-5-5")   # "" disables the fallback
AI_SUMMARY_MODEL = os.environ.get("AI_SUMMARY_MODEL", "claude-haiku-5-5")

AI_MAX_OUTPUT_TOKENS = 1024          # a hard ceiling on one reply: also your worst-case cost per turn
AI_MAX_INPUT_TOKENS = 60_000         # history sent per turn; far below the model's window on purpose (cost)
AI_FIRST_TOKEN_TIMEOUT = 20.0        # seconds to wait for the first word before trying the fallback
AI_SDK_TIMEOUT = 60.0                # per HTTP request. The SDK default is ten minutes: far too long for chat
AI_SDK_MAX_RETRIES = 1               # SDK default is 2. One layer of retries, then fall back
AI_MAX_CONCURRENT_STREAMS = 50       # per process; keep below your provider rate limit divided by processes
AI_DAILY_TOKEN_LIMIT = 200_000       # Chapter 17's per-user daily allowance
