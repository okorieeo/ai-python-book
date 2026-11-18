"""One query with a LEFT JOIN and GROUP BY. In Django this is annotate(Count('messages'))."""


def conversation_summaries(conn):
    rows = conn.execute(
        """
        SELECT c.id, c.title, COUNT(m.id)
        FROM conversation c LEFT JOIN message m ON m.conversation_id = c.id
        GROUP BY c.id, c.title ORDER BY c.id
        """
    ).fetchall()
    return [{"id": i, "title": t, "message_count": n} for i, t, n in rows]
