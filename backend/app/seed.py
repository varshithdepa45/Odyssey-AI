"""Development content: nine placeholder puzzles, hints, and a knowledge base of genuine and decoy records.

    python -m app.seed             seed placeholders if the database has no event
    python -m app.seed --reset     wipe every event first, then seed
    python -m app.seed --private   use the real answers from private/game_secrets.json (git-ignored)

Clue text is generated from each answer with app.ciphers, so the puzzles are solvable as seeded.
"""

import json
import sys
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import ciphers, rag
from .db import SessionLocal, init_db
import math

from .models import Document, Event, Hint, MapMarker, Puzzle
from .security import answer_hash

PRIVATE_FILE = Path(__file__).resolve().parent.parent / "private" / "game_secrets.json"

CAESAR_SHIFT = "7"
VIGENERE_KEY = "EMBER"
BOOK_PASSAGE = """The quick scholars of the valley gathered before the morning bell,
each carrying a jar of ink and a box of puzzles.
They wrote with zeal upon the frozen windows of the old hall,
and whoever solved the final riddle kept the key forever."""

# stage, cipher, title, placeholder answer, cipher key
PUZZLES = [
    (1, "binary", "Signal in Bits", "COPPER FALCON", ""),
    (2, "morse", "Dots and Dashes", "SILENT ORBIT", ""),
    (3, "caesar", "The Emperor's Shift", "NEON HARBOR", CAESAR_SHIFT),
    (4, "polybius", "The Square", "PIXEL GARDEN", ""),
    (5, "vigenere", "The Keyed Lock", "VELVET CIRCUIT", VIGENERE_KEY),
    (6, "hex", "Base Sixteen", "AMBER SIGNAL", ""),
    (7, "braille", "Raised Dots", "LUNAR ARCHIVE", ""),
    (8, "ascii", "Number Codes", "CRIMSON VECTOR", ""),
    (9, "book", "The Founders' Passage", "QUANTUM LANTERN", BOOK_PASSAGE),
]

# Three hints per cipher, from a nudge to a worked method. None of them contains an answer.
HINTS = {
    "binary": ("Each group of eight digits is one character.", "Read each group as a base-2 number, then look it up in an ASCII table.",
               "Write 128 64 32 16 8 4 2 1 above a group and add up the values that sit over a 1."),
    "morse": ("Dots and dashes. A slash separates words.", "The most common letter in English is a single dot.",
              "Write the alphabet beside its Morse codes and match each group between the spaces."),
    "caesar": ("Every letter has moved the same distance along the alphabet.", "The Oracle's archive records the shift. Beware outdated memos.",
               "Take each letter and step backwards by the shift, wrapping round from A to Z."),
    "polybius": ("Each pair of digits points into a 5 by 5 letter grid.", "First digit is the row, second is the column. I and J share a cell.",
                 "Draw the rows A-E, F-K, L-P, Q-U, V-Z and read each pair as row, then column."),
    "vigenere": ("A Caesar cipher whose shift changes with every letter, driven by a keyword.", "The archive names the keyword. Not every record agrees, so cross-check.",
                 "Write the keyword repeatedly under the letters, skipping spaces, and step each letter back by its keyword letter (A is 0)."),
    "hex": ("Pairs of base-16 digits, one pair per character.", "41 is A, 42 is B, and so on.",
            "For each pair, multiply the first digit by 16, add the second, and read the total as an ASCII code."),
    "braille": ("These are braille cells. Find a braille alphabet chart.", "The first ten letters use only the top four dots.",
                "Number the dots 1 to 3 down the left and 4 to 6 down the right, then match each cell to the chart."),
    "ascii": ("Each number is a character code.", "65 is A, 90 is Z, 32 is a space.",
              "Subtract 64 from any number between 65 and 90 to get that letter's place in the alphabet."),
    "book": ("Each triple reads line.word.letter.", "Ask the Oracle for the Founders' Passage, and make sure you have the right edition.",
             "For 2.5.3, go to line 2, count along to the fifth word, and take its third letter."),
}
HINT_COSTS = [10, 20, 30]

# title, kind, stage it unlocks at, content
DOCUMENTS = [
    ("Welcome to the Archive", "genuine", 0,
     "CodeHunt has nine stages. Each stage hides a phrase behind a classic cipher. Decode the phrase and submit it "
     "to unlock the next stage. Spaces and punctuation in an answer do not matter.\n\n"
     "Wrong answers and hints both reduce what a stage is worth, so check your work before you submit. "
     "The archive holds field notes on every cipher. Some records are old, copied badly, or planted, so compare "
     "sources before you trust one."),
    ("Field Notes: Binary", "genuine", 1,
     "Binary writes each character as eight bits. Split the message into groups of eight, convert each group from "
     "base 2 to a number, and read that number as an ASCII character code. 01000001 is 65, which is the letter A."),
    ("Rumour: Seven-Bit Signals", "decoy", 1,
     "A student swears the binary stage uses seven bits per character and that you must drop the first digit of "
     "every group. Nobody has confirmed this."),
    ("Field Notes: Morse Code", "genuine", 2,
     "Morse code spells letters with dots and dashes. In hunt transmissions, a space separates letters and a slash "
     "separates words. E is one dot, T is one dash, S is three dots, O is three dashes."),
    ("Operator's Memo: Reversed Morse", "decoy", 2,
     "Memo from an unknown operator: all Morse in this hunt has been reversed, so read every dot as a dash and "
     "every dash as a dot before decoding."),
    ("Field Notes: The Caesar Shift", "genuine", 3,
     f"The Caesar cipher moves every letter the same number of places along the alphabet. The current hunt encodes "
     f"with a shift of {CAESAR_SHIFT}, so to decode you move each letter back {CAESAR_SHIFT} places. This record was "
     f"confirmed by the hunt committee this season."),
    ("Archived Memo: Shift Thirteen", "decoy", 3,
     "Memo from a previous season: the Caesar stage uses a shift of 13, the classic ROT13. This memo has not been "
     "reviewed since it was filed."),
    ("Field Notes: The Polybius Square", "genuine", 4,
     "The Polybius square places the alphabet in a 5 by 5 grid, filled left to right, top to bottom, with I and J "
     "sharing one cell. Each letter becomes two digits: the row first, then the column. 11 is A, 12 is B, 21 is F."),
    ("Margin Note: Column First", "decoy", 4,
     "Scribbled in a margin: the Polybius square in this hunt is read column first, then row, so 12 is F and 21 is B."),
    ("Field Notes: The Vigenere Lock", "genuine", 5,
     f"The Vigenere cipher shifts each letter by an amount set by a repeating keyword: A shifts by 0, B by 1, and so "
     f"on. The keyword advances only on letters, never on spaces. The committee's keyword for this season is "
     f"{VIGENERE_KEY}. Subtract the keyword letters to decode."),
    ("Overheard: The Frost Keyword", "decoy", 5,
     "Overheard near the notice board: the Vigenere keyword this season is FROST. The person who said it seemed "
     "very sure."),
    ("Field Notes: Hexadecimal", "genuine", 6,
     "Hexadecimal is base 16, using the digits 0 to 9 and the letters A to F. Each pair of hex digits is one ASCII "
     "character code. 41 is the letter A, 5A is Z, and 20 is a space."),
    ("Field Notes: Braille", "genuine", 7,
     "Braille writes each letter as a cell of up to six raised dots, numbered 1 to 3 down the left and 4 to 6 down "
     "the right. A is dot 1, B is dots 1 and 2, C is dots 1 and 4. Letters K to T repeat A to J with dot 3 added."),
    ("Field Notes: ASCII Decimal", "genuine", 8,
     "ASCII gives every character a number. Capital letters run from 65 for A to 90 for Z, and 32 is a space. "
     "The hunt writes these codes in ordinary decimal, separated by spaces."),
    ("Tip Sheet: Offset Codes", "decoy", 8,
     "An anonymous tip sheet claims every ASCII number in the hunt has had 3 added to it, and must be reduced by 3 "
     "before lookup."),
    ("The Founders' Passage (Committee Edition)", "genuine", 9,
     f"The book cipher points into this passage. Each reference is line.word.letter, all counted from 1, and a "
     f"slash separates words. This is the committee's edition, the one the hunt uses.\n\n{BOOK_PASSAGE}"),
    ("The Founders' Passage (Student Reprint)", "decoy", 9,
     "A student reprint of the passage for the book cipher, with references as line.word.letter.\n\n"
     "The young scholars of the hills gathered after the evening bell,\n"
     "each holding a cup of tea and a bag of riddles.\n"
     "They sang with joy beneath the painted ceiling of the new hall,\n"
     "and whoever cracked the last cipher took the prize home."),
]


def _private() -> dict:
    if not PRIVATE_FILE.exists():
        raise SystemExit(f"{PRIVATE_FILE} not found. Copy game_secrets.example.json and fill it in.")
    return json.loads(PRIVATE_FILE.read_text())


def seed_markers(db: Session, event: Event, secrets: dict) -> None:
    """Placeholder map: two public landmarks, one hidden checkpoint per question, and a hidden finale.

    Positions are made up (a ring on the schematic map). Organisers set real names, positions and
    directions in the admin Map tab. With --private, checkpoints take their names from the answers.
    """
    db.add(MapMarker(event_id=event.id, name="Start Point (placeholder)", kind="landmark", unlock="always",
                     x=50, y=88, description="Where the hunt begins."))
    db.add(MapMarker(event_id=event.id, name="Help Desk (placeholder)", kind="landmark", unlock="always",
                     x=14, y=80, description="Find an organiser here if you are stuck."))
    stages = sorted(p.stage for p in db.scalars(select(Puzzle).where(Puzzle.event_id == event.id)))
    for stage in stages:
        angle = 2 * math.pi * (stage - 1) / max(len(stages), 1) - math.pi / 2
        answers = secrets.get("stages", {}).get(str(stage), {}).get("answers")
        db.add(MapMarker(
            event_id=event.id, kind="clue", unlock="stage_solved", unlock_stage=stage,
            name=answers[0].title() if answers else f"Checkpoint {stage} (placeholder)",
            x=round(50 + 36 * math.cos(angle), 1), y=round(46 + 30 * math.sin(angle), 1),
            description=f"Unlocked by solving question {stage}. Collect your paper here.",
        ))
    db.add(MapMarker(event_id=event.id, name="Final Destination (placeholder)", kind="final", unlock="finished",
                     x=50, y=46, description="Shown only to teams that have solved every question."))


def seed(db: Session, private: bool = False) -> bool:
    """Creates the event and its content. Returns False when an event already exists."""
    if db.scalars(select(Event)).first():
        return False
    secrets = _private() if private else {}
    event = Event(
        name="CodeHunt", is_active=True, status="draft", hint_costs=HINT_COSTS, completion_bonus=100,
        final_message=secrets.get(
            "final_message",
            "Placeholder finale. Organisers: set the real closing instructions in the admin dashboard.",
        ),
    )
    db.add(event)
    db.flush()
    for stage, cipher, title, placeholder, key in PUZZLES:
        answers = secrets.get("stages", {}).get(str(stage), {}).get("answers") or [placeholder]
        hints = [Hint(position=i, text=text, penalty=cost) for i, (text, cost) in enumerate(zip(HINTS[cipher], HINT_COSTS), 1)]
        db.add(Puzzle(
            event_id=event.id, stage=stage, title=title, cipher=cipher, points=100,
            prompt="Decode the transmission. The decoded phrase is your answer.",
            encoded_text=ciphers.encode(cipher, answers[0], key),
            answer_hashes=sorted({answer_hash(a) for a in answers}), hints=hints,
        ))
    db.flush()
    seed_markers(db, event, secrets)
    for title, kind, stage, content in DOCUMENTS:
        doc = Document(event_id=event.id, title=title, kind=kind, stage=stage, content=content)
        db.add(doc)
        db.flush()
        rag.index_document(db, doc)
    db.commit()
    return True


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        if "--reset" in sys.argv:
            session.execute(delete(Event))
            session.commit()
        created = seed(session, private="--private" in sys.argv)
    print("Seeded." if created else "An event already exists. Use --reset to start over.")
