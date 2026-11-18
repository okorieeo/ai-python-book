import re

MAX_SPEECH_CHARS = 4000  # stay under typical provider input limits (OpenAI's speech endpoint allows 4096)


def to_speakable(markdown: str) -> str:
    """Text a voice can read. A synthesiser reading "asterisk asterisk" or a URL letter by letter is awful."""
    text = markdown
    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.S)          # fenced code blocks
    text = re.sub(r"`([^`]*)`", r"\1", text)                                   # inline code: keep the words
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)                      # images: keep the alt text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)                       # links: keep the label, drop the URL
    text = re.sub(r"https?://\S+", "a link", text)                             # bare URLs
    text = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]*", "", text, flags=re.M)                  # heading marks
    text = re.sub(r"^[ \t]*[-*+][ \t]+", "", text, flags=re.M)                       # bullets
    text = re.sub(r"^[ \t]*\d+[.)][ \t]+", "", text, flags=re.M)                     # numbered lists
    text = re.sub(r"(\*\*|__|\*|_)(.+?)\1", r"\2", text)                       # bold and italics
    text = re.sub(r"^[ \t]*>[ \t]?", "", text, flags=re.M)                           # quotes
    text = re.sub(r"\|", " ", text)                                            # table bars
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def split_for_speech(text: str, max_chars: int = MAX_SPEECH_CHARS) -> list[str]:
    """Cut at paragraph and sentence ends so every piece sounds natural and fits the provider's limit."""
    if len(text) <= max_chars:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    parts, current = [], ""
    for sentence in sentences:
        while len(sentence) > max_chars:  # one enormous "sentence": cut at a space
            cut = sentence.rfind(" ", 0, max_chars) or max_chars
            cut = cut if cut > 0 else max_chars
            if current:
                parts.append(current); current = ""
            parts.append(sentence[:cut].strip()); sentence = sentence[cut:].strip()
        if len(current) + len(sentence) + 1 > max_chars and current:
            parts.append(current); current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts
