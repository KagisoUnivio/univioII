"""Save reviewed programme options and combine their application checklists."""

import re
from uuid import UUID

from univio.conversation import DOCUMENTS, MATCHES, MENU, Option, Screen

CART = Option("cart", "Application cart")
REQUIREMENTS_LIST = Option("checklist", "My checklist")
CART_LIMIT = 2
ACTION = re.compile(r"(save|remove)-([0-9a-f]{32})")


def cart_command(command: str) -> bool:
    """Recognize only known cart commands and bounded catalogue choice references."""
    return command in ("cart", "checklist") or ACTION.fullmatch(command) is not None


def checklist(rows) -> str:
    """List shared requirements once while preserving programme-specific gaps."""
    current = [row for row in rows if row["available"]]
    fields = sorted({field for row in current for field in row["application_fields"]})
    documents = sorted({doc for row in current for doc in row["application_documents"]})
    sections = ["*Application checklist*"]
    if fields:
        sections.append("Written information: " + ", ".join(fields)[:230])
    if documents:
        sections.append("Documents: " + ", ".join(documents)[:230])
    if not fields and not documents:
        sections.append(
            "No reviewed checklist items are available for your saved options."
        )
    for row in rows:
        name = row["name"][:55]
        if not row["available"]:
            sections.append(f"{name}: deadline passed or source review expired.")
        elif not (row["application_fields"] or row["application_documents"]):
            sections.append(f"{name}: check the university for its full list.")
    sections.append(
        "Check each official source for programme-specific requirements before sending documents."
    )
    return "\n".join(sections)


async def respond_to_cart(conn, key, command, created_at):
    """Run under the onboarding transaction lock scoped to this student."""
    action = ACTION.fullmatch(command)
    notice = ""
    if action:
        accepted = await conn.execute(
            """UPDATE matching_profile SET cart_at=%s, updated_at=now()
               WHERE applicant_key=%s AND (cart_at IS NULL OR cart_at<%s)""",
            (created_at, key, created_at),
        )
        if not accepted.rowcount:
            action = None
            notice = "Showing your current cart.\n"
    if action:
        verb, raw_id = action.groups()
        choice_id = UUID(hex=raw_id)
        if verb == "remove":
            result = await conn.execute(
                "DELETE FROM application_cart WHERE applicant_key=%s AND choice_id=%s",
                (key, choice_id),
            )
            # A retried removal must leave the same state.
            notice = (
                "Programme removed.\n"
                if result.rowcount
                else "Programme is already out of your cart.\n"
            )
        else:
            result = await conn.execute(
                """INSERT INTO application_cart (applicant_key, choice_id)
                   SELECT %s, choice_id FROM programme_rule
                   WHERE choice_id=%s AND reviewed_until>=CURRENT_DATE
                     AND intake_year>=extract(year FROM CURRENT_DATE)
                     AND (closes_on IS NULL OR closes_on>=CURRENT_DATE)
                     AND (SELECT count(*) FROM application_cart WHERE applicant_key=%s)<%s
                   ON CONFLICT DO NOTHING""",
                (key, choice_id, key, CART_LIMIT),
            )
            if result.rowcount:
                notice = "Programme saved.\n"
            else:
                existing = await conn.execute(
                    "SELECT 1 FROM application_cart WHERE applicant_key=%s AND choice_id=%s",
                    (key, choice_id),
                )
                notice = (
                    "Programme is already saved.\n"
                    if await existing.fetchone()
                    else "This option is unavailable or your two-place cart is full.\n"
                )
    cursor = await conn.execute(
        """SELECT r.choice_id, p.name, u.name AS university, r.intake_year,
                  r.source_url, r.application_fields, r.application_documents,
                  r.reviewed_until>=CURRENT_DATE
                    AND r.intake_year>=extract(year FROM CURRENT_DATE)
                    AND coalesce(r.closes_on>=CURRENT_DATE, true) AS available
           FROM application_cart c JOIN programme_rule r USING (choice_id)
           JOIN programme p ON (p.university_code,p.code)=(r.university_code,r.programme_code)
           JOIN university u ON u.code=r.university_code
           WHERE c.applicant_key=%s ORDER BY c.saved_at, r.choice_id""",
        (key,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return Screen(
            notice
            + "Your application cart is empty. Open your matches to save a programme.",
            (MATCHES, MENU),
        )
    if command == "checklist":
        return Screen(checklist(rows), (CART, DOCUMENTS, MENU))
    lines = [
        f"{row['university'][:65]} · {row['name'][:65]} ({row['intake_year']})\n{row['source_url']}"
        for row in rows
    ]
    remove = tuple(
        Option(f"remove-{row['choice_id'].hex}", f"Remove option {i}")
        for i, row in enumerate(rows, 1)
    )
    return Screen(
        notice
        + "*Application cart*\n"
        + "\n\n".join(lines)
        + "\n\nType menu to go back.",
        (REQUIREMENTS_LIST, *remove),
    )
