CREATE TABLE matching_profile (
    applicant_key text PRIMARY KEY,
    stage text CHECK (stage IN ('grade11','grade12','matric')),
    marks text,
    interest text CHECK (interest IN ('science','business','people')),
    stage_at timestamptz,
    marks_at timestamptz,
    interest_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE programme_rule (
    university_code text NOT NULL,
    programme_code text NOT NULL,
    intake_year integer NOT NULL,
    min_aps integer NOT NULL CHECK (min_aps BETWEEN 0 AND 42),
    subjects jsonb NOT NULL,
    interest text NOT NULL CHECK (interest IN ('science','business','people')),
    source_url text NOT NULL CHECK (source_url LIKE 'https://%' AND length(source_url) <= 160),
    reviewed_until date NOT NULL,
    PRIMARY KEY (university_code, programme_code, intake_year),
    FOREIGN KEY (university_code, programme_code) REFERENCES programme(university_code, code)
);

CREATE TABLE funding_opportunity (
    code text NOT NULL,
    name text NOT NULL,
    intake_year integer NOT NULL,
    interest text CHECK (interest IN ('science','business','people')),
    min_aps integer CHECK (min_aps BETWEEN 0 AND 42),
    closes_on date NOT NULL,
    reviewed_until date NOT NULL,
    source_url text NOT NULL CHECK (source_url LIKE 'https://%' AND length(source_url) <= 200),
    PRIMARY KEY (code, intake_year)
);
