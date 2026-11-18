from dataclasses import dataclass, field

@dataclass
class Message:
    role: str
    content: str
    tags: list[str] = field(default_factory=list)

m = Message(role="user", content="Hello")
print(m)                       # Message(role='user', content='Hello', tags=[])
