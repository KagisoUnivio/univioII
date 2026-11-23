-- Reference institutions only. Verify programme rules separately before publishing.
BEGIN;
INSERT INTO university (code, name, official_url) VALUES
    ('uct', 'University of Cape Town', 'https://www.uct.ac.za/'),
    ('up', 'University of Pretoria', 'https://www.up.ac.za/'),
    ('wits', 'University of the Witwatersrand', 'https://www.wits.ac.za/')
ON CONFLICT (code) DO NOTHING;
COMMIT;
