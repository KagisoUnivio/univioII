ALTER TABLE programme_rule ADD COLUMN choice_id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE;
ALTER TABLE programme_rule ADD COLUMN closes_on date;
ALTER TABLE programme_rule ADD COLUMN application_fields text[] NOT NULL DEFAULT '{}';
ALTER TABLE programme_rule ADD COLUMN application_documents text[] NOT NULL DEFAULT '{}';
ALTER TABLE matching_profile ADD COLUMN cart_at timestamptz;

CREATE TABLE application_cart (
    applicant_key text NOT NULL REFERENCES matching_profile(applicant_key) ON DELETE CASCADE,
    choice_id uuid NOT NULL REFERENCES programme_rule(choice_id),
    saved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (applicant_key, choice_id)
);
