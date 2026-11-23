# Student onboarding and matching

The WhatsApp home screen offers **Find my matches** and guest exploration.
Matching asks for the school stage, then six subject marks with optional Life
Orientation. Students can choose a study interest or view results immediately.
Returning to **Find my matches** resumes from saved progress. Use **School
stage** to change the stage, and **Enter marks** from results to correct marks.
Funding is optional. Students can see screened opportunities before uploading
any identity document or providing financial details.

## How results work

The initial rules support a 42-point APS calculated from six subjects with
Life Orientation excluded. Import only requirements for institutions and
programmes using that exact scoring model. Institutions with different points
tables or special treatment of subjects need their own tested scoring strategy.
For an example of a university publishing intake-specific requirements, see
[University of Pretoria's 2027 BSc Computer Science page](https://www.up.ac.za/eece/programmes/undergraduate/bsc-computer-science/2027).

Programme screening checks APS and subject percentages. It distinguishes
listed thresholds met, close options, and missing subject information. Grade 11
and Grade 12 results are labelled provisional. The two best displayed options
include the intake and source. Use institution requirements to confirm other
conditions, such as deadlines, interviews or language rules.

Funding rows require a source, an intake and an open deadline. The shortlist
uses the student's APS and optional subject-area preference. Students check
financial, residency and other provider criteria separately. Keep dated source
evidence during review. Exclude expired and unverified rules.

## Enable and test

1. Apply migrations through `004_application_cart.sql` using the migration login.
2. Give the worker SELECT, INSERT, UPDATE and DELETE on `matching_profile` and
   SELECT on `university`, `programme`, `programme_rule` and
   `funding_opportunity`. Give catalogue writers separate credentials.
   The worker also needs SELECT, INSERT and DELETE on `application_cart`.
3. Set the same independent `MATCHING_PROFILE_SECRET` (at least 32 characters)
   in Secrets Manager for API and worker. Keep it stable across deployments.
   Changing it without a migration makes old profiles inaccessible.
4. For a disposable PostgreSQL database ending in `_test`, apply
   `seeds/002_demo_catalog.sql`, then `seeds/003_demo_matching.sql`.
   Use a test WhatsApp recipient and send the sample marks shown in chat, choose
   **Science & tech**, and then **Find funding**. Expect a synthetic computing
   programme and bursary. Keep demo data out of deployed student catalogues.
5. Before enabling for real students, confirm the relevant student privacy
   notices, retention and deletion procedures. Populate the initial verified
   catalogue, review it against official sources and validate the journey
   through Meta staging.

## Data and code

Students can save two programmes from results, remove a saved option, and see
a combined checklist. Reviewed shared requirements appear once. The checklist
distinguishes expired options and missing checklist data. It lists what may be
needed and does not record written answers or certify uploaded files.

Pull catalogue candidates from the legacy Data directory in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m univio.catalogue inventory 'C:\Users\Sharon Jomon\OneDrive - Chisl Group\Projects\Personal\univio\Data'
```

The output is an unreviewed inventory. Prepare a separate JSON batch with
`universities`, `programmes` and `funding` arrays using the schemas in
`src/univio/catalogue.py`. Confirm intake dates, scoring model, percentage
thresholds, sources and checklist entries manually. Run
`python -m univio.catalogue validate reviewed.json`, then
`python -m univio.catalogue publish reviewed.json` with
`CATALOGUE_DATABASE_URL` set to the catalogue writer login.

- `matching.py` canonicalizes allowed subject marks, computes APS and explains
  the screening result. Arbitrary free text is excluded.
- `onboarding.py` handles each profile step and queries reviewed programmes
  and funding rows. The worker keys profiles with a phone-scoped HMAC and uses
  a transaction lock plus event timestamps to protect corrections from retries.
- Pending inbox entries may contain validated marks. Terminal processing clears
  the command, recipient and media ID. Profiles expire after 30 days without an
  update, with cleanup performed by enabled workers. Apply a separate retention
  policy to database backups.
- `tests/test_matching.py` checks scoring boundaries and exercises a saved
  profile, stale update protection, resuming, and funding with real PostgreSQL.
