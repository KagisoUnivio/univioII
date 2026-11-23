"""Pure conversation decisions and shared copy; no network, state or storage.

Each screen owns its options. The same options generate buttons and text-command
help, so the two interfaces cannot silently drift apart.
"""

from dataclasses import dataclass

from univio.career import QUESTIONS, career_result


@dataclass(frozen=True)
class Option:
    command: str
    label: str


@dataclass(frozen=True)
class Screen:
    text: str
    options: tuple[Option, ...]

    def render(self) -> str:
        """Keep every button action usable with a typed command too."""
        commands = " | ".join(option.command for option in self.options)
        return f"{self.text}\n\nTap a button or type: {commands}."


MENU = Option("menu", "Main menu")
EXPLORE = Option("explore", "Explore options")
REQUIREMENTS = Option("requirements", "Entry requirements")
HELP = Option("help", "Get help")
DOCUMENTS = Option("documents", "Documents")
MATCHES = Option("matches", "Find my matches")
FUNDING = Option("funding", "Find funding")
ENTER_MARKS = Option("marks", "Enter marks")
INTEREST = Option("interests", "Study interests")
DOCUMENT_TYPES = {
    "id": "applicant ID",
    "matric": "matric results",
    "grade11": "Grade 11 results",
}

SCREENS = {
    "menu": Screen(
        "*Welcome to Univio*\nExplore your next study step, without registering. What would you like help with?",
        (MATCHES, EXPLORE, HELP),
    ),
    "explore": Screen(
        "*Explore study options*\nWhich area interests you? You can explore another area at any time.",
        (
            Option("science", "Science & tech"),
            Option("business", "Business"),
            Option("people", "People & society"),
        ),
    ),
    "requirements": Screen(
        "*Entry requirements*\nWhat would you like to understand? Type menu to return to the main menu.",
        (
            Option("aps", "Understand APS"),
            Option("subjects", "Subject choices"),
            Option("prepare", "Application prep"),
        ),
    ),
    "science": Screen(
        "*Science & technology*\nExplore computing, engineering and natural sciences. Compare the subjects and work involved, then check each institution's current prospectus for subject and mark requirements.\n\nThese are exploration ideas, not personalised admission matches.",
        (EXPLORE, REQUIREMENTS, MENU),
    ),
    "business": Screen(
        "*Business*\nExplore accounting, economics, management and entrepreneurship. Compare programme content and professional accreditation, then check the institution's current admission requirements.\n\nThese are exploration ideas, not personalised admission matches.",
        (EXPLORE, REQUIREMENTS, MENU),
    ),
    "people": Screen(
        "*People & society*\nExplore education, humanities, social sciences and law. Think about the problems you enjoy solving, then compare programme content and current admission requirements.\n\nThese are exploration ideas, not personalised admission matches.",
        (EXPLORE, REQUIREMENTS, MENU),
    ),
    "aps": Screen(
        "*Understand APS*\nAn Admission Point Score summarises school results for admissions. Institutions and programmes can calculate it differently, including how they treat Life Orientation.\n\nUse the institution's current scoring table. Meeting a score alone does not guarantee admission.",
        (REQUIREMENTS, Option("subjects", "Subject choices"), MENU),
    ),
    "subjects": Screen(
        "*Subject choices*\nCheck the exact programme's required subjects, minimum marks and language requirements. Mathematics and Mathematical Literacy are not interchangeable for every programme.\n\nUse the latest official prospectus before making subject choices.",
        (REQUIREMENTS, Option("prepare", "Application prep"), MENU),
    ),
    "prepare": Screen(
        "*Application preparation*\n1. Shortlist programmes.\n2. Confirm current requirements and deadlines on official institution sites.\n3. Check which documents and fees are required.\n4. Submit through the official application portal and keep your reference number.\n\nDo not send identity documents, passwords or payment details to this chat.",
        (DOCUMENTS, REQUIREMENTS, MENU),
    ),
    "help": Screen(
        "*How Univio works*\nUse buttons or the commands shown below. Type menu, back or cancel to return to the main menu. Screened results are guidance. Confirm requirements with the institution.",
        (DOCUMENTS, REQUIREMENTS, Option("career", "Career quiz")),
    ),
    "documents": Screen(
        "*Prepare your documents*\nCheck the university's checklist first. "
        "Have a clear PDF or photo ready for each required item. "
        "Only share your own documents and leave out bank details and passwords.",
        (
            Option("upload", "Upload instructions"),
            Option("prepare", "Application prep"),
            MENU,
        ),
    ),
    "upload": Screen(
        "*Upload one file at a time*\nAttach a PDF, JPG or PNG up to 10 MB. "
        "In the caption, enter one of these labels:\n"
        + "\n".join(f"• {code} for {label}" for code, label in DOCUMENT_TYPES.items())
        + "\nOnly send it if you want Univio to store a private copy for application preparation.",
        (DOCUMENTS, MENU),
    ),
    "matches": Screen(
        "Matching needs a configured student profile service. You can explore study options here.",
        (
            EXPLORE,
            Option("school-stage", "School stage"),
            Option("cart", "Application cart"),
        ),
    ),
    "cart": Screen(
        "Your cart is available when the application matching service is enabled.",
        (Option("checklist", "My checklist"), MATCHES, MENU),
    ),
    "career": Screen(
        "*Career quiz*\nPick one letter per question. Reply with seven letters in order, for example quiz riaseic.\n"
        + "\n".join(
            f"{number}. {question}" for number, question in enumerate(QUESTIONS, 1)
        ),
        (EXPLORE, MENU),
    ),
    "checklist": Screen(
        "Open your application cart to view a checklist.",
        (Option("cart", "Application cart"), MENU),
    ),
    "school-stage": Screen(
        "*Find my matches*\nChoose your school stage. Univio uses your subjects and marks to screen options and retains your matching profile for up to 30 days of inactivity. You can browse without sharing marks.",
        (
            Option("grade11", "Grade 11"),
            Option("grade12", "Grade 12"),
            Option("matric", "Finished matric"),
        ),
    ),
    "grade11": Screen("Use your latest Grade 11 results.", (ENTER_MARKS, MENU)),
    "grade12": Screen("Use your latest Grade 12 results.", (ENTER_MARKS, MENU)),
    "matric": Screen("Use your final matric results.", (ENTER_MARKS, INTEREST, MENU)),
    "marks": Screen(
        "*Enter six subjects and marks*\nSend one message like this (leave out names and ID numbers):\n"
        "marks eng=72 maths=68 science=66 life=75 history=70 afr=65\n"
        "Use mathslit for Mathematical Literacy. Life Orientation is optional as lo=70.",
        (Option("subjects-help", "Subject codes"), MATCHES, MENU),
    ),
    "subjects-help": Screen(
        "Codes: eng (English), afr, zul, xho, sot, tsn, nso, tso, ven, nde, ssw (languages), maths, mathslit, science (Physical Sciences), life (Life Sciences), accounting, business, economics, history, geography, cat, it, lo.",
        (ENTER_MARKS, MENU),
    ),
    "interests": Screen(
        "*Choose a study interest*\nThis moves relevant programmes higher in your results.",
        (
            Option("match-science", "Science & tech"),
            Option("match-business", "Business"),
            Option("match-people", "People & society"),
        ),
    ),
    "match-science": Screen("Science and technology.", (MATCHES, FUNDING, MENU)),
    "match-business": Screen("Business.", (MATCHES, FUNDING, MENU)),
    "match-people": Screen("People and society.", (MATCHES, FUNDING, MENU)),
    "funding": Screen(
        "Funding screening needs a configured student profile service.", (MATCHES, MENU)
    ),
}

ALIASES = {
    "hi": "menu",
    "hello": "menu",
    "start": "menu",
    "back": "menu",
    "cancel": "menu",
    "stop": "menu",
}
RECOVERY = "I couldn't match that choice. Please choose an option below. Your messages are not saved as a profile."
OLD_FORM = "We've replaced forms with simpler chat menus. Please choose where you'd like to go next."
UNSUPPORTED = "I can help with text and menu choices. Please don't upload personal documents here."
UPLOAD_UNAVAILABLE = Screen(
    "Document uploads are unavailable. Keep your file and try again later.",
    (DOCUMENTS, MENU),
)


def choose_screen(command: str | None, kind: str = "text") -> Screen:
    """Resolve only known actions; never echo or execute arbitrary user input."""
    if kind == "old_form":
        return Screen(OLD_FORM, SCREENS["menu"].options)
    if kind == "unsupported":
        return Screen(UNSUPPORTED, SCREENS["menu"].options)
    normalized = (command or "").strip().casefold()
    normalized = ALIASES.get(normalized, normalized)
    if normalized.startswith("quiz ") and kind == "text":
        result = career_result(normalized)
        return Screen(result, (EXPLORE, MATCHES, MENU)) if result else SCREENS["career"]
    if kind == "upload" or normalized == "upload":
        return UPLOAD_UNAVAILABLE
    return SCREENS.get(normalized, Screen(RECOVERY, SCREENS["menu"].options))
