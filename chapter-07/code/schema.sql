-- ===== ACCOUNTS =====
CREATE TABLE users (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id   UUID        NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    email       TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    role        TEXT        NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
CREATE UNIQUE INDEX users_email_active_uniq ON users (lower(email)) WHERE deleted_at IS NULL;

-- ===== CHAT =====
CREATE TABLE conversations (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id   UUID        NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    user_id     BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL DEFAULT 'New conversation',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_conversations_user_updated ON conversations (user_id, updated_at DESC);

CREATE TABLE messages (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id  BIGINT      NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT        NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content          TEXT        NOT NULL,
    model            TEXT,                                   -- which AI model answered
    input_tokens     INTEGER     CHECK (input_tokens  >= 0),
    output_tokens    INTEGER     CHECK (output_tokens >= 0),
    metadata         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_conversation_created ON messages (conversation_id, created_at);

CREATE TABLE usage_records (                 -- append-only ledger of token usage
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id     BIGINT      REFERENCES messages(id) ON DELETE SET NULL,
    input_tokens   INTEGER     NOT NULL CHECK (input_tokens  >= 0),
    output_tokens  INTEGER     NOT NULL CHECK (output_tokens >= 0),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_usage_user_created ON usage_records (user_id, created_at);

-- ===== BILLING =====
CREATE TABLE plans (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                 TEXT   NOT NULL UNIQUE,            -- 'free', 'pro'
    name                 TEXT   NOT NULL,
    price_cents          INTEGER NOT NULL CHECK (price_cents >= 0),
    currency             CHAR(3) NOT NULL,                  -- 'USD', 'NGN'
    billing_interval     TEXT   NOT NULL CHECK (billing_interval IN ('month', 'year', 'one_time')),
    monthly_token_limit  BIGINT NOT NULL CHECK (monthly_token_limit > 0),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE subscriptions (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                   BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    plan_id                   BIGINT      NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
    provider                  TEXT        NOT NULL CHECK (provider IN ('stripe', 'paystack')),
    provider_subscription_id  TEXT        NOT NULL,
    status                    TEXT        NOT NULL CHECK (status IN ('trialing', 'active', 'past_due', 'canceled')),
    current_period_end        TIMESTAMPTZ,
    cancel_at_period_end      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_subscription_id)
);
-- at most ONE live subscription per user
CREATE UNIQUE INDEX one_live_subscription_per_user
    ON subscriptions (user_id) WHERE status IN ('trialing', 'active', 'past_due');

CREATE TABLE payments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subscription_id     BIGINT      REFERENCES subscriptions(id) ON DELETE RESTRICT,   -- NULL for one-time payments
    provider            TEXT        NOT NULL CHECK (provider IN ('stripe', 'paystack')),
    provider_reference  TEXT        NOT NULL,
    amount_cents        BIGINT      NOT NULL CHECK (amount_cents > 0),
    currency            CHAR(3)     NOT NULL,
    status              TEXT        NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed', 'refunded')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_reference)
);
CREATE INDEX idx_payments_user_created ON payments (user_id, created_at DESC);

CREATE TABLE webhook_events (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider      TEXT        NOT NULL,
    event_id      TEXT        NOT NULL,
    event_type    TEXT        NOT NULL,
    payload       JSONB       NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,
    UNIQUE (provider, event_id)
);

-- ===== DOCUMENTS (used from Chapter 31) =====
CREATE TABLE documents (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id    UUID        NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    user_id      BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename     TEXT        NOT NULL,
    storage_key  TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'uploaded'
                 CHECK (status IN ('uploaded', 'processing', 'ready', 'failed')),
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_documents_user ON documents (user_id, created_at DESC);

CREATE TABLE document_chunks (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id  BIGINT  NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT    NOT NULL,
    UNIQUE (document_id, chunk_index)
    -- the embedding column is added in Chapter 31 with the pgvector extension:
    -- ALTER TABLE document_chunks ADD COLUMN embedding vector(1536);
);
