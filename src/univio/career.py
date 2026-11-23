"""Seven-question RIASEC exploration adapted from the legacy career form."""

import re
from collections import Counter

QUIZ = re.compile(r"quiz ([riasec]{6}[eic])")
HINTS = {
    "r": "Practical · engineering, construction, or technical trades",
    "i": "Investigative · science, computing, or research",
    "a": "Creative · design, media, or the arts",
    "s": "Social · education, health, or community work",
    "e": "Enterprising · business, marketing, or entrepreneurship",
    "c": "Organised · accounting, operations, or information management",
}
QUESTIONS = (
    "What do you enjoy? R build · I investigate · A create · S help · E lead · C organise",
    "Favourite subjects? R technical · I maths/science · A arts/languages · S history/geography · E economics · C accounting",
    "How do you work best? R hands-on · I independently · A freely · S with people · E leading · C in a structured setting",
    "What matters most? R visible results · I discovery · A expression · S helping people · E influence · C stability",
    "What comes naturally? R tools · I analysis · A ideas · S listening · E persuasion · C accuracy",
    "Where would you work? R workshop · I lab · A studio · S school/clinic · E company · C office/data centre",
    "Which risk level fits? E high · I medium · C low",
)


def career_result(command: str) -> str | None:
    match = QUIZ.fullmatch(command)
    if not match:
        return None
    counts = Counter(match[1])
    ranked = sorted(counts, key=lambda code: (-counts[code], "riasec".index(code)))
    lines = "\n".join(HINTS[code] for code in ranked[:2])
    return f"*Career interests to explore*\n{lines}\n\nUse these as starting points and check programme requirements separately."
