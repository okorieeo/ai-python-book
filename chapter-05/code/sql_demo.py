import sqlite3

conn = sqlite3.connect(":memory:")          # a temporary database in memory
conn.execute("PRAGMA foreign_keys = ON")    # SQLite needs this to enforce foreign keys
conn.row_factory = sqlite3.Row              # rows behave like dictionaries

conn.executescript("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL
);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL
);
""")

# Insert with PLACEHOLDERS (?), never by pasting values into the SQL text
conn.execute("INSERT INTO users (email, name) VALUES (?, ?)", ("ada@example.com", "Ada"))
conn.execute("INSERT INTO conversations (user_id, title) VALUES (?, ?)", (1, "Learning SQL"))
conn.executemany(
    "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
    [(1, "user", "What is a join?"), (1, "assistant", "A join combines rows from two tables.")],
)
conn.commit()

query = """
SELECT c.title, m.role, m.content
FROM conversations c JOIN messages m ON m.conversation_id = c.id
WHERE c.user_id = ?
ORDER BY m.id
"""
for row in conn.execute(query, (1,)):
    print(f"[{row['title']}] {row['role']}: {row['content']}")

# Constraints in action
try:
    conn.execute("INSERT INTO users (email, name) VALUES (?, ?)", ("ada@example.com", "Copy"))
except sqlite3.IntegrityError as error:
    print("Rejected duplicate email:", error)

conn.execute("DELETE FROM users WHERE id = 1")     # cascades to conversations and messages
print("messages left:", conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
