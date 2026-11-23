"""WhatsApp onboarding backed by a short-lived, pseudonymous academic profile."""

import hmac
import os

from univio.cart import CART, cart_command, respond_to_cart
from univio.conversation import (
    ENTER_MARKS,
    EXPLORE,
    FUNDING,
    INTEREST,
    MATCHES,
    MENU,
    SCREENS,
    Option,
    Screen,
)
from univio.matching import INTERESTS, STAGES, programme_fit, scores


def profile_secret() -> str:
    """The same configuration gates mark acceptance and worker processing."""
    secret = os.environ.get("MATCHING_PROFILE_SECRET", "")
    if secret and len(secret.strip()) < 32:
        raise ValueError("MATCHING_PROFILE_SECRET must have at least 32 characters")
    return secret


class Onboarding:
    def __init__(self, pool, secret: str):
        self.pool = pool
        self.secret = secret

    async def respond(self, job) -> Screen | None:
        """Apply one validated step and return the next screen or result."""
        command = job["command"]
        if job["kind"] not in ("text", "selection") or not command:
            return None
        if command not in (
            *STAGES,
            "school-stage",
            "matches",
            "marks-help",
            "funding",
            "interests",
            *(f"match-{item}" for item in INTERESTS),
        ) and not (command.startswith("marks ") or cart_command(command)):
            return None
        if command == "marks-help":
            return SCREENS["marks"]
        if command == "school-stage":
            return SCREENS["school-stage"]
        key = hmac.digest(
            self.secret.encode(),
            f"{job['phone_id']}:{job['recipient']}".encode(),
            "sha256",
        ).hex()
        async with self.pool.connection() as conn:
            # Serialize profile steps and prevent retries of older messages
            # from replacing answers the student has since corrected.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,)
            )
            await conn.execute(
                "DELETE FROM matching_profile WHERE applicant_key=%s AND updated_at <= now()-interval '30 days'",
                (key,),
            )
            cursor = await conn.execute(
                "SELECT * FROM matching_profile WHERE applicant_key=%s", (key,)
            )
            profile = await cursor.fetchone()
            if command in STAGES:
                await conn.execute(
                    """INSERT INTO matching_profile (applicant_key,stage,stage_at) VALUES (%s,%s,%s)
                       ON CONFLICT (applicant_key) DO UPDATE SET stage=excluded.stage,
                       stage_at=excluded.stage_at, updated_at=now()
                       WHERE matching_profile.stage_at IS NULL OR matching_profile.stage_at < excluded.stage_at""",
                    (key, command, job["created_at"]),
                )
                return SCREENS[command]
            if not profile:
                return SCREENS["school-stage"]
            if cart_command(command):
                return await respond_to_cart(conn, key, command, job["created_at"])
            if command.startswith("marks "):
                await conn.execute(
                    """UPDATE matching_profile SET marks=%s, marks_at=%s, updated_at=now()
                       WHERE applicant_key=%s AND (marks_at IS NULL OR marks_at < %s)""",
                    (command, job["created_at"], key, job["created_at"]),
                )
                return Screen(
                    "Marks saved. Choose an interest or see matches now.",
                    (INTEREST, MATCHES, MENU),
                )
            if command.startswith("match-"):
                interest = command.removeprefix("match-")
                cursor = await conn.execute(
                    """UPDATE matching_profile SET interest=%s, interest_at=%s, updated_at=now()
                       WHERE applicant_key=%s AND (interest_at IS NULL OR interest_at < %s)
                       RETURNING interest""",
                    (interest, job["created_at"], key, job["created_at"]),
                )
                if await cursor.fetchone():
                    profile["interest"] = interest
            if not profile["marks"]:
                return SCREENS["marks"]
            if command == "interests":
                return SCREENS["interests"]
            aps, marks = scores(profile["marks"])
            if command == "funding":
                return await self.funding(conn, aps, profile["interest"])
            return await self.programmes(conn, aps, marks, profile)

    @staticmethod
    async def programmes(conn, aps, marks, profile):
        cursor = await conn.execute(
            """SELECT p.name, u.name AS university, r.*
               FROM programme_rule r JOIN programme p
               ON (p.university_code,p.code)=(r.university_code,r.programme_code)
               JOIN university u ON u.code=r.university_code
               WHERE r.reviewed_until >= CURRENT_DATE
                 AND r.intake_year >= extract(year FROM CURRENT_DATE)
                 AND (r.closes_on IS NULL OR r.closes_on >= CURRENT_DATE)
                 AND r.min_aps <= %s
               ORDER BY r.intake_year, u.code, p.code""",
            (aps + 2,),
        )
        hits = []
        async for rule in cursor:
            fit = programme_fit(aps, marks, rule)
            if fit:
                rank, reason = fit
                hits.append(
                    (
                        rank,
                        rule["interest"] != profile["interest"],
                        rule["intake_year"],
                        f"{rule['university'][:50]} · {rule['name'][:55]} ({rule['intake_year']})\n{reason[:90]}\n{rule['source_url']}",
                        rule["choice_id"],
                    )
                )
        heading = f"*Programme screening* · APS {aps}"
        if profile["stage"] != "matric":
            heading += " (provisional marks)"
        if not hits:
            return Screen(
                heading
                + "\nNo close options in the reviewed catalogue. Browse study ideas or check official prospectuses.",
                (EXPLORE, FUNDING, ENTER_MARKS),
            )
        selected = sorted(hits)[:2]
        lines = "\n\n".join(item[3] for item in selected)
        save = tuple(
            Option(f"save-{item[4].hex}", f"Save option {i}")
            for i, item in enumerate(selected, 1)
        )
        return Screen(
            f"{heading}\n{lines}\n\nType funding, interests or marks to continue. Confirm details with the university.",
            (*save, CART),
        )

    @staticmethod
    async def funding(conn, aps, interest):
        cursor = await conn.execute(
            """SELECT name,intake_year,closes_on,source_url FROM funding_opportunity
               WHERE reviewed_until>=CURRENT_DATE AND closes_on>=CURRENT_DATE
                 AND intake_year>=extract(year FROM CURRENT_DATE)
                 AND (min_aps IS NULL OR min_aps<=%s)
                 AND (interest IS NULL OR interest=%s)
               ORDER BY closes_on,code LIMIT 2""",
            (aps, interest),
        )
        rows = await cursor.fetchall()
        if not rows:
            return Screen(
                "No reviewed funding options fit the details we have. Try your institution's funding office.",
                (MATCHES, INTEREST, MENU),
            )
        lines = "\n\n".join(
            f"{row['name'][:90]} ({row['intake_year']}) · closes {row['closes_on']}\n{row['source_url']}"
            for row in rows
        )
        return Screen(
            f"*Funding options to check*\n{lines}\n\nCheck all provider rules, including financial and residency criteria.",
            (MATCHES, MENU),
        )
