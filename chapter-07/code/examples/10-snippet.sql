-- Page 1
SELECT id, created_at, content FROM messages
WHERE conversation_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 50;

-- Next page: pass the created_at and id of the last row you received
SELECT id, created_at, content FROM messages
WHERE conversation_id = 7
  AND (created_at, id) < ('2026-11-01 09:30:00+00', 1234)
ORDER BY created_at DESC, id DESC
LIMIT 50;
