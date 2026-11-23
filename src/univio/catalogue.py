"""Inventory legacy data and validate a separately reviewed launch catalogue."""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from univio.config import DatabaseConfig
from univio.matching import SUBJECTS
from univio.runtime import run_async

Code = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]
Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
]
Source = Annotated[
    str, StringConstraints(pattern=r"^https://[^\s/]+(?:/[^\s]*)?$", max_length=160)
]
Interest = Literal["science", "business", "people"]
APS = Annotated[int, Field(ge=0, le=42)]
Year = Annotated[int, Field(ge=2026, le=2100)]


class Row(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class University(Row):
    code: Code
    name: Label
    official_url: Source


class Programme(Row):
    university_code: Code
    code: Code
    name: Label
    intake_year: Year
    scoring: Literal["six-subject-42"]
    min_aps: APS
    subjects: dict[str, Annotated[int, Field(ge=0, le=100)]] = Field(max_length=8)
    interest: Interest
    source_url: Source
    closes_on: date
    reviewed_until: date
    application_fields: list[Label] = Field(default_factory=list, max_length=12)
    application_documents: list[Label] = Field(default_factory=list, max_length=12)


class Funding(Row):
    code: Code
    name: Label
    intake_year: Year
    interest: Interest | None = None
    min_aps: APS | None = None
    source_url: Source
    closes_on: date
    reviewed_until: date


class Catalogue(Row):
    universities: list[University]
    programmes: list[Programme]
    funding: list[Funding]

    def check_references(self) -> None:
        keys = {item.code for item in self.universities}
        programmes = {
            (item.university_code, item.code, item.intake_year)
            for item in self.programmes
        }
        funding = {(item.code, item.intake_year) for item in self.funding}
        if (
            len(keys) != len(self.universities)
            or len(programmes) != len(self.programmes)
            or len(funding) != len(self.funding)
        ):
            raise ValueError("Duplicate catalogue identity")
        for item in self.programmes:
            if item.university_code not in keys or item.subjects.keys() - SUBJECTS:
                raise ValueError(
                    "Programme contains an unknown university or subject code"
                )


def walk_programmes(node):
    """Walk nested legacy faculties, including UJ's nested containers."""
    if isinstance(node, list):
        for child in node:
            yield from walk_programmes(child)
    elif isinstance(node, dict):
        for key, child in node.items():
            if key.lower() in ("programmes", "programs") and isinstance(child, list):
                yield from (row for row in child if isinstance(row, dict))
            elif isinstance(child, (dict, list)):
                yield from walk_programmes(child)


def inventory(data_dir: Path) -> dict:
    """Produce candidates for review without executing legacy code or changing a DB."""
    if not data_dir.is_dir():
        raise ValueError("Pass the legacy Data directory")
    programmes, funding = [], []
    for path in sorted(data_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if path.name == "bursaries_raw.json":
            funding.extend(
                {key: row.get(key) for key in ("title", "source_url", "closing_date")}
                for row in raw
                if isinstance(row, dict)
            )
        elif isinstance(raw, dict):
            for institution in raw.get("institutions", [raw]):
                name = institution.get("name", institution.get("university"))
                for item in walk_programmes(institution.get("faculties", {})):
                    programmes.append(
                        {
                            "file": path.name,
                            "university": name,
                            "name": item.get("name")
                            or item.get("programme")
                            or item.get("programme_name"),
                            "requirements": item.get("minimum_requirements")
                            or item.get("requirements"),
                        }
                    )
    return {
        "status": "unreviewed",
        "programme_candidates": programmes,
        "funding_candidates": funding,
    }


async def publish(catalogue: Catalogue, config: DatabaseConfig) -> None:
    """Apply reviewed rows atomically while preserving existing cart IDs."""
    catalogue.check_references()
    async with await AsyncConnection.connect(
        config.url, **config.connection_kwargs()
    ) as conn:
        for item in catalogue.universities:
            await conn.execute(
                """INSERT INTO university VALUES (%s,%s,%s) ON CONFLICT (code)
                   DO UPDATE SET name=excluded.name, official_url=excluded.official_url""",
                (item.code, item.name, item.official_url),
            )
        for item in catalogue.programmes:
            await conn.execute(
                """INSERT INTO programme (university_code,code,name,source_url,verified_at)
                   VALUES (%s,%s,%s,%s,CURRENT_DATE) ON CONFLICT (university_code,code)
                   DO UPDATE SET name=excluded.name, source_url=excluded.source_url, verified_at=CURRENT_DATE""",
                (item.university_code, item.code, item.name, item.source_url),
            )
            await conn.execute(
                """INSERT INTO programme_rule
                   (university_code,programme_code,intake_year,min_aps,subjects,interest,source_url,
                    reviewed_until,closes_on,application_fields,application_documents)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (university_code,programme_code,intake_year) DO UPDATE SET
                   min_aps=excluded.min_aps, subjects=excluded.subjects, interest=excluded.interest,
                   source_url=excluded.source_url, reviewed_until=excluded.reviewed_until,
                   closes_on=excluded.closes_on, application_fields=excluded.application_fields,
                   application_documents=excluded.application_documents""",
                (
                    item.university_code,
                    item.code,
                    item.intake_year,
                    item.min_aps,
                    Jsonb(item.subjects),
                    item.interest,
                    item.source_url,
                    item.reviewed_until,
                    item.closes_on,
                    item.application_fields,
                    item.application_documents,
                ),
            )
        for item in catalogue.funding:
            await conn.execute(
                """INSERT INTO funding_opportunity
                   (code,name,intake_year,interest,min_aps,closes_on,reviewed_until,source_url)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (code,intake_year) DO UPDATE SET
                   name=excluded.name, interest=excluded.interest, min_aps=excluded.min_aps,
                   closes_on=excluded.closes_on, reviewed_until=excluded.reviewed_until,
                   source_url=excluded.source_url""",
                (
                    item.code,
                    item.name,
                    item.intake_year,
                    item.interest,
                    item.min_aps,
                    item.closes_on,
                    item.reviewed_until,
                    item.source_url,
                ),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inventory", "validate", "publish"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.action == "inventory":
        print(json.dumps(inventory(args.path), ensure_ascii=True, indent=2))
        return
    catalogue = Catalogue.model_validate_json(args.path.read_bytes())
    catalogue.check_references()
    if args.action == "publish":
        run_async(
            publish(
                catalogue, DatabaseConfig.from_environment("CATALOGUE_DATABASE_URL")
            )
        )
    print(
        f"{args.action}: {len(catalogue.programmes)} programmes, {len(catalogue.funding)} funding opportunities"
    )


if __name__ == "__main__":
    main()
