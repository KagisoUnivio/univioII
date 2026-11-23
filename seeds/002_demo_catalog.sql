-- Synthetic data for a disposable local or CI database.
BEGIN;
DO $$
BEGIN
    IF current_database() !~ '_test$' THEN
        RAISE EXCEPTION 'Demo seed requires an isolated database ending in _test';
    END IF;
END
$$;
INSERT INTO university (code, name, official_url)
VALUES ('demo', 'Example University (synthetic)', 'https://example.invalid/')
ON CONFLICT (code) DO NOTHING;
INSERT INTO programme (university_code, code, name)
VALUES ('demo', 'demo-computing', 'Example Computing Programme (synthetic)')
ON CONFLICT (university_code, code) DO NOTHING;
COMMIT;
