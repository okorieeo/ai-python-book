CREATE TABLE credit_ledger (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    delta       BIGINT NOT NULL,                  -- +1000 purchase, -35 usage, +500 refund
    reason      TEXT   NOT NULL,                  -- 'purchase', 'usage', 'refund', 'bonus'
    reference   TEXT,                             -- payment id, message id...
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ledger_user ON credit_ledger (user_id, created_at);

-- balance
SELECT COALESCE(SUM(delta), 0) FROM credit_ledger WHERE user_id = 42;
