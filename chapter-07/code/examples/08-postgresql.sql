EXPLAIN ANALYZE
SELECT SUM(input_tokens + output_tokens)
FROM usage_records
WHERE user_id = 42 AND created_at >= '2026-11-01';
