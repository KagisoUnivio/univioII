"""Academic screening for explicitly reviewed six-subject APS rules."""

import re

SUBJECTS = frozenset(
    [
        "eng",
        "afr",
        "zul",
        "xho",
        "sot",
        "tsn",
        "nso",
        "tso",
        "ven",
        "nde",
        "ssw",
        "maths",
        "mathslit",
        "science",
        "life",
        "accounting",
        "business",
        "economics",
        "history",
        "geography",
        "cat",
        "it",
        "lo",
    ]
)
STAGES = ("grade11", "grade12", "matric")
INTERESTS = ("science", "business", "people")


def canonical_marks(text: str) -> str | None:
    """Return canonical marks without retaining extra free text or identifiers."""
    parts = text.split()
    if not parts or parts[0] != "marks" or len(parts) not in (7, 8):
        return None
    marks = {}
    for part in parts[1:]:
        match = re.fullmatch(r"([a-z]+)=([0-9]{1,3})", part)
        if not match:
            return None
        subject, raw = match.groups()
        if subject not in SUBJECTS or subject in marks or int(raw) > 100:
            return None
        marks[subject] = int(raw)
    if len(marks.keys() - {"lo"}) != 6 or {"maths", "mathslit"} <= marks.keys():
        return None
    return "marks " + " ".join(
        f"{subject}={mark}" for subject, mark in sorted(marks.items())
    )


def scores(command: str) -> tuple[int, dict[str, int]]:
    """Calculate the supported APS method, excluding Life Orientation."""
    marks = {
        subject: int(mark)
        for subject, mark in (part.split("=") for part in command.split()[1:])
    }
    levels = (30, 40, 50, 60, 70, 80)
    aps = sum(
        1 + sum(mark >= level for level in levels)
        for subject, mark in marks.items()
        if subject != "lo"
    )
    return aps, marks


def programme_fit(
    aps: int, marks: dict[str, int], rule: dict
) -> tuple[int, str] | None:
    """Rank clear matches first, then close options and missing-subject checks."""
    thresholds = rule["subjects"]
    if not isinstance(thresholds, dict) or any(
        subject not in SUBJECTS or type(minimum) is not int or not 0 <= minimum <= 100
        for subject, minimum in thresholds.items()
    ):
        return None
    aps_gap = max(0, rule["min_aps"] - aps)
    if aps_gap > 2:
        return None
    deficits = {
        subject: minimum - marks[subject]
        for subject, minimum in thresholds.items()
        if subject in marks and marks[subject] < minimum
    }
    if len(deficits) > 1 or any(gap > 5 for gap in deficits.values()):
        return None
    missing = thresholds.keys() - marks.keys()
    if missing:
        return 2, "Check subject data: " + ", ".join(sorted(missing))
    if not aps_gap and not deficits:
        return 0, f"Listed thresholds met (APS minimum {rule['min_aps']})"
    reasons = ([f"{aps_gap} APS short"] if aps_gap else []) + [
        f"{subject} {gap} percentage points short" for subject, gap in deficits.items()
    ]
    return 1, "Near match: " + ", ".join(reasons)
