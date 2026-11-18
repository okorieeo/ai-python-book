"""Build the core AI-chat SaaS schema in SQLite and test the rules we designed."""
import json
import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("PRAGMA foreign_keys = ON")
conn.row_factory = sqlite3.Row

conn.executescript("""
CREATE TABLE users (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE plans (
    id                   INTEGER PRIMARY KEY,
    code                 TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    price_cents          INTEGER NOT NULL CHECK (price_cents >= 0),
    currency             TEXT NOT NULL,
    monthly_token_limit  INTEGER NOT NULL CHECK (monthly_token_limit > 0)
);

CREATE TABLE subscriptions (
    id                       INTEGER PRIMARY KEY,
    user_id                  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id                  INTEGER NOT NULL REFERENCES plans(id),
    provider                 TEXT NOT NULL CHECK (provider IN ('stripe', 'paystack')),
    provider_subscription_id TEXT NOT NULL,
    status                   TEXT NOT NULL CHECK (status IN ('trialing', 'active', 'past_due', 'canceled')),
    created_at               TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, provider_subscription_id)
);
-- A user may have at most ONE live subscription (partial unique index)
CREATE UNIQUE INDEX one_live_subscription_per_user
    ON subscriptions (user_id) WHERE status IN ('trialing', 'active', 'past_due');

CREATE TABLE webhook_events (
    id           INTEGER PRIMARY KEY,
    provider     TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    received_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    UNIQUE (provider, event_id)
);

CREATE TABLE usage_records (
    id             INTEGER PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    input_tokens   INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens  INTEGER NOT NULL CHECK (output_tokens >= 0),
    created_at     TEXT NOT NULL
);
""")

# ---- sample data
conn.execute("INSERT INTO users (email, name) VALUES ('ada@example.com', 'Ada')")
conn.execute("INSERT INTO plans (code, name, price_cents, currency, monthly_token_limit) VALUES ('pro', 'Pro', 1900, 'USD', 1000000)")
conn.execute("INSERT INTO subscriptions (user_id, plan_id, provider, provider_subscription_id, status) VALUES (1, 1, 'stripe', 'sub_1', 'active')")

# ---- Rule 1: only one live subscription per user
try:
    conn.execute("INSERT INTO subscriptions (user_id, plan_id, provider, provider_subscription_id, status) VALUES (1, 1, 'paystack', 'SUB_9', 'active')")
except sqlite3.IntegrityError as error:
    print("Rule 1 OK (second live subscription rejected):", error)

# a canceled one is allowed (history is kept)
conn.execute("INSERT INTO subscriptions (user_id, plan_id, provider, provider_subscription_id, status) VALUES (1, 1, 'paystack', 'SUB_old', 'canceled')")
print("Rule 1 OK (canceled history allowed)")

# ---- Rule 2: webhooks are processed once (idempotency via UNIQUE + ON CONFLICT DO NOTHING)
def record_event(provider, event_id, event_type, payload):
    cur = conn.execute(
        "INSERT INTO webhook_events (provider, event_id, event_type, payload) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (provider, event_id) DO NOTHING",
        (provider, event_id, event_type, json.dumps(payload)),
    )
    return cur.rowcount == 1          # True only the first time

print("Rule 2 first delivery processed:", record_event("stripe", "evt_1", "invoice.paid", {"amount": 1900}))
print("Rule 2 duplicate delivery processed:", record_event("stripe", "evt_1", "invoice.paid", {"amount": 1900}))

# ---- Rule 3: usage ledger and monthly limit
rows = [(1, 4000, 800, "2026-11-01 09:00:00"), (1, 6000, 1200, "2026-11-02 10:00:00"), (1, 5000, 500, "2026-10-30 10:00:00")]
conn.executemany("INSERT INTO usage_records (user_id, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?)", rows)

used = conn.execute("""
    SELECT COALESCE(SUM(input_tokens + output_tokens), 0) AS used
    FROM usage_records
    WHERE user_id = ? AND created_at >= ? AND created_at < ?
""", (1, "2026-11-01", "2026-12-01")).fetchone()["used"]
limit = conn.execute("""
    SELECT p.monthly_token_limit FROM subscriptions s JOIN plans p ON p.id = s.plan_id
    WHERE s.user_id = ? AND s.status IN ('trialing', 'active', 'past_due')
""", (1,)).fetchone()[0]
print(f"Rule 3 November usage: {used} of {limit} tokens ({used / limit:.1%})")

# ---- Rule 4: bad data is rejected by CHECK constraints
for sql, label in [
    ("INSERT INTO plans (code, name, price_cents, currency, monthly_token_limit) VALUES ('bad', 'Bad', -5, 'USD', 10)", "negative price"),
    ("INSERT INTO users (email, name, role) VALUES ('x@example.com', 'X', 'superuser')", "invalid role"),
    ("INSERT INTO usage_records (user_id, input_tokens, output_tokens, created_at) VALUES (999, 1, 1, '2026-11-01')", "unknown user"),
]:
    try:
        conn.execute(sql)
    except sqlite3.IntegrityError as error:
        print(f"Rule 4 OK ({label} rejected): {error}")

# ---- Indexes: look at the query plan before and after
for i in range(5000):
    conn.execute("INSERT INTO usage_records (user_id, input_tokens, output_tokens, created_at) VALUES (?, 10, 10, '2026-11-03')", (1,))
query = "SELECT SUM(input_tokens) FROM usage_records WHERE user_id = 1 AND created_at >= '2026-11-01'"
print("Plan without index:", conn.execute("EXPLAIN QUERY PLAN " + query).fetchone()["detail"])
conn.execute("CREATE INDEX idx_usage_user_created ON usage_records (user_id, created_at)")
print("Plan with index:   ", conn.execute("EXPLAIN QUERY PLAN " + query).fetchone()["detail"])
