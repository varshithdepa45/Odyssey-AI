"""Apply pending database migrations: python -m app.migrate"""

from .db import init_db
from .migrations import LATEST

if __name__ == "__main__":
    init_db()
    print(f"Database is at schema version {LATEST}.")
