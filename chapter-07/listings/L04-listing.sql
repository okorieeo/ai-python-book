CREATE TABLE farms (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- farm_members (see section 7.3) links users to farms with a role

CREATE TABLE devices (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    farm_id       BIGINT NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    kind          TEXT   NOT NULL CHECK (kind IN ('temperature', 'humidity', 'camera', 'feeder')),
    name          TEXT   NOT NULL,
    last_seen_at  TIMESTAMPTZ
);
CREATE INDEX idx_devices_farm ON devices (farm_id);

CREATE TABLE sensor_readings (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id    BIGINT           NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    recorded_at  TIMESTAMPTZ      NOT NULL,
    value        DOUBLE PRECISION NOT NULL
);
CREATE INDEX idx_readings_device_time ON sensor_readings (device_id, recorded_at DESC);
