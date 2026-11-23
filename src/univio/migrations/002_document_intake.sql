ALTER TABLE inbox ADD COLUMN media_id text;

CREATE TABLE document_intake (
    event_key text PRIMARY KEY,
    applicant_key text NOT NULL,
    document_type text NOT NULL CHECK (document_type IN ('id', 'matric', 'grade11')),
    object_key text NOT NULL UNIQUE,
    content_type text NOT NULL,
    byte_count integer NOT NULL CHECK (byte_count BETWEEN 1 AND 10485760),
    received_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE university (
    code text PRIMARY KEY,
    name text NOT NULL,
    official_url text NOT NULL CHECK (official_url LIKE 'https://%')
);

CREATE TABLE programme (
    university_code text REFERENCES university(code),
    code text,
    name text NOT NULL,
    source_url text,
    verified_at date,
    PRIMARY KEY (university_code, code)
);
