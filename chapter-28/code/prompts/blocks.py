"""Building blocks for prompt text: cleaning, escaping and wrapping untrusted data."""
import re
import unicodedata

# Anything that looks like an XML/HTML tag: <name>, </name>, <name attr="x">
_TAG_LIKE = re.compile(r"<(/?[A-Za-z_][^<>]{0,200})>")
# Odd spellings of our own wrapper, such as "< / Untrusted_Data >", are escaped as well.
_OWN_TAG = re.compile(r"<(?=\s*/?\s*untrusted_data)", re.I)


def clean_prompt_text(value: str, *, max_chars: int) -> str:
    """Normalize text that is about to enter a prompt. Raises ValueError if too long.

    Removes control characters (except newline and tab), normalizes Unicode and trims
    the ends. The same idea as clean_text in Chapter 17, kept dependency-free here so
    the tests in this chapter run on their own.
    """
    if not isinstance(value, str):
        raise TypeError("Prompt text must be a string.")
    value = unicodedata.normalize("NFC", value)
    value = "".join(
        ch for ch in value if unicodedata.category(ch) != "Cc" or ch in "\t\n"
    )
    value = value.strip()
    if len(value) > max_chars:
        raise ValueError(f"Prompt text may not be longer than {max_chars} characters.")
    return value


def escape_tags(text: str) -> str:
    """Make tag-like text harmless so it cannot close or open one of our wrappers.

    "</untrusted_data>" becomes "&lt;/untrusted_data&gt;". Other text is untouched.
    """
    text = _TAG_LIKE.sub(lambda m: "&lt;" + m.group(1) + "&gt;", text)
    return _OWN_TAG.sub("&lt;", text)


def xml_block(tag: str, content: str, **attrs: str) -> str:
    """Wrap content in <tag attr="value">...</tag>. Use for text YOU wrote."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", tag):
        raise ValueError(f"Bad tag name: {tag!r}")
    attr_text = "".join(f' {key}="{value}"' for key, value in attrs.items())
    return f"<{tag}{attr_text}>\n{content}\n</{tag}>"


def wrap_untrusted(label: str, text: str) -> str:
    """Wrap text that someone else wrote (documents, web pages, transcripts, tool results).

    Tag-like text inside is escaped first, so the data cannot end the wrapper early.
    The system prompt tells the model that anything inside <untrusted_data> is
    material to work on, never instructions to follow.
    """
    return xml_block("untrusted_data", escape_tags(text), label=label)
