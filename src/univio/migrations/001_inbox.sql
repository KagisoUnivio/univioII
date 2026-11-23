CREATE TABLE inbox (
    event_key text PRIMARY KEY,
    phone_id text NOT NULL,
    recipient text,
    event_timestamp bigint NOT NULL,
    command text,
    kind text NOT NULL,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','sent','dead')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    lease_token uuid,
    error_kind text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX inbox_pending ON inbox (available_at) WHERE state IN ('pending','processing');
CREATE INDEX inbox_retention ON inbox (updated_at) WHERE state IN ('sent','dead');

-- Hello World.
