-- Create
INSERT INTO users (email, name) VALUES ('ada@example.com', 'Ada');

-- Read
SELECT id, name FROM users WHERE email = 'ada@example.com';
SELECT * FROM messages WHERE conversation_id = 3 ORDER BY created_at LIMIT 50;

-- Update
UPDATE users SET name = 'Ada Lovelace' WHERE id = 1;

-- Delete
DELETE FROM messages WHERE id = 10;

-- Join: combine related tables
SELECT c.title, m.role, m.content
FROM conversations c
JOIN messages m ON m.conversation_id = c.id
WHERE c.user_id = 1
ORDER BY m.created_at;

-- Aggregate: count messages per conversation
SELECT c.id, c.title, COUNT(m.id) AS message_count
FROM conversations c
LEFT JOIN messages m ON m.conversation_id = c.id
GROUP BY c.id, c.title
ORDER BY message_count DESC;
