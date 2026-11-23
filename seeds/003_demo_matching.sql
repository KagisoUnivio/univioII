BEGIN;
DO $$
BEGIN
    IF current_database() !~ '_test$' THEN
        RAISE EXCEPTION 'Demo matching requires an isolated database ending in _test';
    END IF;
END
$$;
INSERT INTO programme_rule
    (university_code, programme_code, intake_year, min_aps, subjects, interest, source_url, reviewed_until)
VALUES
    ('demo', 'demo-computing', extract(year FROM CURRENT_DATE)::int + 1,
     25, '{"maths":60,"eng":50}', 'science', 'https://example.invalid/programme', CURRENT_DATE + 60)
ON CONFLICT DO NOTHING;

INSERT INTO funding_opportunity
    (code, name, intake_year, interest, min_aps, closes_on, reviewed_until, source_url)
VALUES
    ('demo-funding', 'Example bursary (synthetic)', extract(year FROM CURRENT_DATE)::int + 1,
     'science', 25, CURRENT_DATE + 45, CURRENT_DATE + 45, 'https://example.invalid/funding')
ON CONFLICT DO NOTHING;
COMMIT;
