"""Symptom: a user sees tags that belong to somebody else's earlier request."""


def add_tag(tag: str, tags: list = []) -> list:
    tags.append(tag)
    return tags
