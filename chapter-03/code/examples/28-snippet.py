def greet(name: str, times: int = 1) -> str:
    return (f"Hello, {name}! " * times).strip()

prices: dict[str, float] = {"basic": 9.99, "pro": 29.0}
tags: list[str] = ["ai", "python"]
maybe_name: str | None = None           # either a str or None

def find_user(user_id: int) -> dict | None:
    """Return the user or None if not found."""
    ...
