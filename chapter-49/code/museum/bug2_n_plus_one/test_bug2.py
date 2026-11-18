import sqlite3
import unittest

from museum.impl import load

impl = load("museum.bug2_n_plus_one", ("buggy", "fixed"))


def make_db(conversations=50, messages_each=3):
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE conversation (id INTEGER PRIMARY KEY, title TEXT);"
        "CREATE TABLE message (id INTEGER PRIMARY KEY, conversation_id INTEGER, content TEXT);"
    )
    for c in range(1, conversations + 1):
        conn.execute("INSERT INTO conversation VALUES (?, ?)", (c, f"Chat {c}"))
        for m in range(messages_each):
            conn.execute("INSERT INTO message (conversation_id, content) VALUES (?, ?)", (c, f"m{m}"))
    conn.commit()
    return conn


class ListQueryTests(unittest.TestCase):
    def test_counts_are_right(self):
        conn = make_db(3, 2)
        conn.execute("INSERT INTO conversation VALUES (99, 'Empty')")
        result = impl.conversation_summaries(conn)
        self.assertEqual([r["message_count"] for r in result], [2, 2, 2, 0])  # empty chats must still appear

    def test_query_count_does_not_grow_with_the_number_of_conversations(self):  # regression test
        conn = make_db(50)
        queries = []
        conn.set_trace_callback(queries.append)
        impl.conversation_summaries(conn)
        self.assertLessEqual(len(queries), 2, f"{len(queries)} queries for 50 conversations")


if __name__ == "__main__":
    unittest.main()
