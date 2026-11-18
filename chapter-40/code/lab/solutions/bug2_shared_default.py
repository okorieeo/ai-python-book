def add_tag(tag: str, tags: list | None = None) -> list:
    tags = [] if tags is None else tags      # a default list is created once, at definition time
    tags.append(tag)
    return tags
