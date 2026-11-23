# Legacy migration status

Reference snapshot: `370244e` from the November 23 pull. The old checkout is
the reference for student-facing behavior and tests. This service keeps PyWa,
PostgreSQL, and S3 as the integration boundaries.

| Legacy feature | Status in univioII |
|---|---|
| Academic onboarding, marks and study interest | Core journey implemented, with one supported APS method and an expiring profile. Legacy registration forms, extended preferences and institution-specific scoring remain. |
| Programme catalogue | Inventory reads the old source files. Reviewed catalogue publication preserves existing cart IDs. Real named intake rows still require source review before publication. |
| Bursaries | Basic screening implemented. Extended evidence rules, saving, reminders and opted-in alerts remain. |
| Application cart and master requirements | Saved choices, removal and combined reviewed checklist implemented. The first version holds two choices. Written answers, per-programme completion tracking and document approval remain. |
| Document vault | S3 quarantine intake and RDS receipts exist. Scan status, stakeholder viewing, replacement and deletion workflows remain. |
| Career quiz | Seven-question RIASEC chat version implemented. Legacy faculty-level programme links remain. |
| PDFs, multilingual navigation, Ask Univio | Pending integration with the new profile and catalogue. |
| Portal status checks and preview pilots | Pending institution-specific integration and test accounts. Live submission is a separate capability. |

The old sources contain proposed form-field lists and heterogeneous academic
rules. The catalogue importer never publishes the unreviewed inventory. Keep
the pilot to one reviewed intake first. See [matching](matching.md) for the
commands, schema, migration and database grants.
