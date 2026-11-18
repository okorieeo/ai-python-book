CREATE TABLE farm_members (
    farm_id    BIGINT NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT   NOT NULL CHECK (role IN ('owner', 'manager', 'worker')),
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (farm_id, user_id)
);
