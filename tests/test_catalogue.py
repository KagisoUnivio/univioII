"""Review boundary for legacy catalogue candidates."""

import json
import os
from datetime import date, timedelta

import pytest
from psycopg.conninfo import conninfo_to_dict
from pydantic import ValidationError

from univio.catalogue import Catalogue, inventory, publish
from univio.config import DatabaseConfig
from univio.inbox import Inbox
from univio.migrate import migrate
from univio.runtime import run_async


def test_inventory_cannot_be_published_as_reviewed_catalogue(tmp_path):
    (tmp_path / "legacy.json").write_text(
        json.dumps(
            {
                "university": "Example",
                "faculties": {
                    "nested": {
                        "school": {
                            "programmes": [
                                {
                                    "name": "Example computing",
                                    "requirements": {"aps": 26},
                                }
                            ]
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = inventory(tmp_path)
    assert result["programme_candidates"][0]["name"] == "Example computing"
    with pytest.raises(ValidationError):
        Catalogue.model_validate(result)


@pytest.mark.postgres
def test_reviewed_publication_preserves_choice_identity():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is unset")
    assert conninfo_to_dict(url)["dbname"].endswith("_test")
    now = date.today()

    async def scenario():
        config = DatabaseConfig(url)
        await migrate(config)
        catalogue = Catalogue.model_validate(
            {
                "universities": [
                    {
                        "code": "publication-test",
                        "name": "Test Institute",
                        "official_url": "https://example.invalid",
                    }
                ],
                "programmes": [
                    {
                        "university_code": "publication-test",
                        "code": "demo",
                        "name": "Test Programme",
                        "intake_year": now.year + 1,
                        "scoring": "six-subject-42",
                        "min_aps": 42,
                        "subjects": {"maths": 75},
                        "interest": "science",
                        "source_url": "https://example.invalid/programme",
                        "closes_on": now + timedelta(days=30),
                        "reviewed_until": now + timedelta(days=30),
                        "application_documents": ["Test transcript"],
                    }
                ],
                "funding": [],
            }
        )
        inbox = Inbox(config)
        await inbox.open()
        try:
            await publish(catalogue, config)
            async with inbox.pool.connection() as conn:
                query = "SELECT choice_id, application_documents, min_aps FROM programme_rule WHERE university_code='publication-test'"
                first = await (await conn.execute(query)).fetchone()
            catalogue.programmes[0].min_aps = 41
            await publish(catalogue, config)
            async with inbox.pool.connection() as conn:
                second = await (await conn.execute(query)).fetchone()
            assert first["choice_id"] == second["choice_id"]
            assert second["application_documents"] == ["Test transcript"]
            assert second["min_aps"] == 41
        finally:
            await inbox.close()

    run_async(scenario())
