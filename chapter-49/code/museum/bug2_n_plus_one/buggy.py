"""Bug 2: the conversation list is slow. One query for the list, then one more per row (N+1)."""


def conversation_summaries(conn):
    rows = conn.execute("SELECT id, title FROM conversation ORDER BY id").fetchall()
    out = []
    for conv_id, title in rows:
        (count,) = conn.execute("SELECT COUNT(*) FROM message WHERE conversation_id = ?", (conv_id,)).fetchone()
        out.append({"id": conv_id, "title": title, "message_count": count})
    return out
