import os
from prompts.registry import PromptRegistry

PROMPT_REGISTRY = PromptRegistry(
    BASE_DIR / "prompt_library",
    active={
        # an unset variable means "use the highest version"
        name: os.environ[f"PROMPT_PIN_{name.upper()}"]
        for name in ("summarize_conversation", "chat_assistant")
        if os.environ.get(f"PROMPT_PIN_{name.upper()}")
    },
)
