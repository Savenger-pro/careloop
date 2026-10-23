"""CareLoop core logic: people, medications, dose logs, check-ins.

Pure Python + SQLite so it is easy to test and has no extra dependencies.
Every public function returns a dict with a short `speech` string plus
structured data.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get(
    "CARELOOP_DB",
    os.path.join(os.path.dirname(__file__), "careloop.db"),
)
TZ = ZoneInfo(os.environ.get("CARELOOP_TZ", "Asia/Dhaka"))
GRACE_MINUTES = int(os.environ.get("CARELOOP_GRACE_MIN", "60"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons(
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE COLLATE NOCASE NOT NULL,
    relationship TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meds(
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    name TEXT NOT NULL COLLATE NOCASE,
    dose TEXT DEFAULT '',
    times TEXT NOT NULL,
    notes TEXT DEFAULT '',
    active INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS dose_logs(
    id INTEGER PRIMARY KEY,
    med_id INTEGER NOT NULL REFERENCES meds(id),
    slot TEXT NOT NULL,
    taken INTEGER NOT NULL,
    logged_at TEXT NOT NULL,
    note TEXT DEFAULT '',
    UNIQUE(med_id, slot)
);

CREATE TABLE IF NOT EXISTS checkins(
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    mood INTEGER NOT NULL,
    symptoms TEXT DEFAULT '',
    note TEXT DEFAULT '',
    logged_at TEXT NOT NULL
);
"""


def now() -> datetime:
    """Return the current time, or the demo/test override."""
    override = os.environ.get("CARELOOP_NOW")

    if override:
        value = datetime.fromisoformat(override)

        if value.tzinfo is None:
            return value.replace(tzinfo=TZ)

        return value.astimezone(TZ)

    return datetime.now(TZ)


def db() -> sqlite3.Connection:
    """Open the SQLite database and ensure the schema exists."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)

    cols = [
        row["name"]
        for row in con.execute("PRAGMA table_info(meds)")
    ]

    if "created_at" not in cols:
        con.execute("ALTER TABLE meds ADD COLUMN created_at TEXT")

    return con


class CareError(ValueError):
    """User-facing error for invalid names, times, and similar inputs."""


def _person(con, name: str) -> sqlite3.Row:
    """Find a person by name or raise a helpful error."""
    row = con.execute(
        "SELECT * FROM persons WHERE name = ?",
        (name.strip(),),
    ).fetchone()

    if not row:
        known = [
            item["name"]
            for item in con.execute(
                "SELECT name FROM persons ORDER BY name"
            )
        ]

        hint = f" I know: {', '.join(known)}." if known else " Add them first."

        raise CareError(f"I don't have anyone called {name}.{hint}")

    return row


def _meds_for(con, person_id: int, name: str | None = None):
    """Return active medications for a person."""
    query = (
        "SELECT * FROM meds "
        "WHERE person_id = ? AND active = 1"
    )
    args = [person_id]

    if name:
        query += " AND name = ?"
        args.append(name.strip())

    return con.execute(
        query + " ORDER BY name",
        args,
    ).fetchall()


def _parse_times(times: list[str]) -> list[str]:
    """Validate and normalize 24-hour medication times."""
    output = []

    for value in times:
        try:
            hour, minute = value.strip().split(":")
            normalized = f"{int(hour):02d}:{int(minute):02d}"

            datetime.strptime(normalized, "%H:%M")
            output.append(normalized)

        except (ValueError, AttributeError):
            raise CareError(
                f"'{value}' is not a valid time. "
                "Use 24-hour HH:MM like 08:00 or 20:30."
            ) from None

    if not output:
        raise CareError("Give at least one time, like 08:00.")

    return sorted(set(output))


def _spoken_time(hhmm: str) -> str:
    """Format a time for speech, compatible with Windows and other OSes."""
    value = datetime.strptime(hhmm, "%H:%M")
    formatted = value.strftime("%I:%M %p").lstrip("0")
    return formatted.replace(":00 ", " ")


# ---------------------------------------------------------------------
# People and medications
# ---------------------------------------------------------------------

def add_person(name: str, relationship: str = "") -> dict:
    """Add a person to the care circle."""
    with db() as con:
        try:
            con.execute(
                "INSERT INTO persons(name, relationship) VALUES (?, ?)",
                (name.strip(), relationship),
            )
        except sqlite3.IntegrityError:
            raise CareError(
                f"{name} is already in your care circle."
            ) from None

    return {
        "speech": f"Added {name} to your care circle.",
        "name": name,
        "relationship": relationship,
    }


def add_medication(
    person: str,
    medication: str,
    times: list[str],
    dose: str = "",
    notes: str = "",
    start: datetime | None = None,
) -> dict:
    """Add a medication and its scheduled times."""
    times = _parse_times(times)

    with db() as con:
        person_row = _person(con, person)

        if _meds_for(con, person_row["id"], medication):
            raise CareError(
                f"{person_row['name']} already has {medication}. "
                "Remove it first to change the times."
            )

        con.execute(
            """
            INSERT INTO meds(
                person_id, name, dose, times, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                person_row["id"],
                medication.strip(),
                dose,
                json.dumps(times),
                notes,
                (start or now()).isoformat(timespec="seconds"),
            ),
        )

    spoken = " and ".join(_spoken_time(value) for value in times)

    return {
        "speech": (
            f"Okay. {person_row['name']} will take "
            f"{medication} at {spoken}."
        ),
        "person": person_row["name"],
        "medication": medication,
        "dose": dose,
        "times": times,
    }


def remove_medication(person: str, medication: str) -> dict:
    """Deactivate a person's medication."""
    with db() as con:
        person_row = _person(con, person)

        cursor = con.execute(
            """
            UPDATE meds
            SET active = 0
            WHERE person_id = ? AND name = ? AND active = 1
            """,
            (person_row["id"], medication.strip()),
        )

        if not cursor.rowcount:
            raise CareError(
                f"{person_row['name']} isn't taking {medication}."
            )

    return {
        "speech": f"Removed {medication} for {person_row['name']}."
    }


# ---------------------------------------------------------------------
# Medication schedule
# ---------------------------------------------------------------------

def _slots_for_day(med: sqlite3.Row, day: datetime):
    """Generate scheduled datetime slots for a medication."""
    for value in json.loads(med["times"]):
        hour, minute = map(int, value.split(":"))

        yield day.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )


def _status(
    slot: datetime,
    log: sqlite3.Row | None,
    at: datetime,
) -> str:
    """Determine the status of a scheduled dose."""
    if log is not None:
        return "taken" if log["taken"] else "skipped"

    if at > slot + timedelta(minutes=GRACE_MINUTES):
        return "missed"

    if at >= slot - timedelta(minutes=30):
        return "due"

    return "upcoming"


def _day_rows(
    con,
    person: sqlite3.Row,
    day: datetime,
    at: datetime,
):
    """Build the scheduled dose rows for a person and a day."""
    rows = []

    for med in _meds_for(con, person["id"]):
        started = (
            datetime.fromisoformat(med["created_at"])
            if med["created_at"]
            else None
        )

        for slot in _slots_for_day(med, day):
            if started and slot < started.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            ):
                continue

            key = slot.strftime("%Y-%m-%d %H:%M")

            log = con.execute(
                """
                SELECT * FROM dose_logs
                WHERE med_id = ? AND slot = ?
                """,
                (med["id"], key),
            ).fetchone()

            rows.append({
                "medication": med["name"],
                "dose": med["dose"],
                "time": slot.strftime("%H:%M"),
                "slot": key,
                "status": _status(slot, log, at),
                "note": log["note"] if log else "",
                "_med_id": med["id"],
            })

    return sorted(
        rows,
        key=lambda row: (row["time"], row["medication"]),
    )


def today_schedule(person: str) -> dict:
    """Return today's medication schedule."""
    at = now()

    with db() as con:
        person_row = _person(con, person)
        rows = _day_rows(con, person_row, at, at)

    for row in rows:
        row.pop("_med_id", None)

    if not rows:
        return {
            "speech": (
                f"{person_row['name']} has no medications scheduled."
            ),
            "person": person_row["name"],
            "doses": [],
        }

    pending = [
        row for row in rows
        if row["status"] in ("due", "upcoming", "missed")
    ]

    if not pending:
        speech = (
            f"All done. {person_row['name']} has finished "
            "every dose for today."
        )
    else:
        next_dose = pending[0]
        count = len(pending)
        dose_word = "dose" if count == 1 else "doses"

        speech = (
            f"{person_row['name']} has {count} {dose_word} left today. "
            f"Next is {next_dose['medication']} at "
            f"{_spoken_time(next_dose['time'])}"
        )

        if next_dose["status"] == "missed":
            speech += ", which is overdue."
        else:
            speech += "."

    return {
        "speech": speech,
        "person": person_row["name"],
        "date": at.strftime("%Y-%m-%d"),
        "doses": rows,
    }


def log_dose(
    person: str,
    medication: str,
    taken: bool = True,
    note: str = "",
) -> dict:
    """Record a dose against the closest eligible slot today."""
    at = now()

    with db() as con:
        person_row = _person(con, person)
        medications = _meds_for(
            con,
            person_row["id"],
            medication,
        )

        if not medications:
            raise CareError(
                f"{person_row['name']} isn't taking {medication}."
            )

        medication_id = medications[0]["id"]

        open_rows = [
            row
            for row in _day_rows(con, person_row, at, at)
            if row["_med_id"] == medication_id
            and row["status"] not in ("taken", "skipped")
        ]

        if not open_rows:
            return {
                "speech": (
                    f"{medication} is already logged "
                    "for every slot today."
                ),
                "already_logged": True,
            }

        # Prefer the most recent due or overdue slot.
        overdue = [
            row for row in open_rows
            if row["status"] in ("due", "missed")
        ]

        if overdue:
            target = max(overdue, key=lambda row: row["slot"])
        else:
            target = min(open_rows, key=lambda row: row["slot"])

        con.execute(
            """
            INSERT INTO dose_logs(
                med_id, slot, taken, logged_at, note
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                target["_med_id"],
                target["slot"],
                int(taken),
                at.isoformat(timespec="seconds"),
                note,
            ),
        )

    if taken:
        verb = "Logged"
    else:
        verb = "Marked as skipped:"

    return {
        "speech": (
            f"{verb} {medication} for {person_row['name']}, "
            f"{_spoken_time(target['time'])} dose."
        ),
        "person": person_row["name"],
        "medication": medication,
        "slot": target["slot"],
        "taken": taken,
    }


def missed_doses(person: str, days: int = 1) -> dict:
    """List missed medication doses over the requested number of days."""
    at = now()
    missed = []

    with db() as con:
        person_row = _person(con, person)

        for offset in range(max(0, days)):
            day = at - timedelta(days=offset)

            missed.extend(
                row
                for row in _day_rows(con, person_row, day, at)
                if row["status"] == "missed"
            )

    for row in missed:
        row.pop("_med_id", None)

    if not missed:
        return {
            "speech": f"No missed doses for {person_row['name']}.",
            "person": person_row["name"],
            "missed": [],
        }

    names = ", ".join(
        sorted({row["medication"] for row in missed})
    )

    count = len(missed)
    dose_word = "dose" if count == 1 else "doses"

    return {
        "speech": (
            f"{person_row['name']} missed {count} {dose_word}: {names}. "
            "Please check in with them and, if you're unsure what to do, "
            "ask their doctor or pharmacist."
        ),
        "person": person_row["name"],
        "missed": missed,
    }


# ---------------------------------------------------------------------
# Check-ins and weekly summary
# ---------------------------------------------------------------------

def log_checkin(
    person: str,
    mood: int,
    symptoms: str = "",
    note: str = "",
) -> dict:
    """Record a person's mood and any reported symptoms."""
    if not 1 <= mood <= 5:
        raise CareError(
            "Mood must be a number from 1 (very low) to 5 (great)."
        )

    at = now()

    with db() as con:
        person_row = _person(con, person)

        con.execute(
            """
            INSERT INTO checkins(
                person_id, mood, symptoms, note, logged_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                person_row["id"],
                mood,
                symptoms,
                note,
                at.isoformat(timespec="seconds"),
            ),
        )

    speech = (
        f"Noted. {person_row['name']}'s mood is {mood} out of 5."
    )

    if mood <= 2 or symptoms:
        speech += (
            " Keep an eye on them, and contact a doctor "
            "if you're worried."
        )

    return {
        "speech": speech,
        "person": person_row["name"],
        "mood": mood,
        "symptoms": symptoms,
    }


def weekly_summary(person: str) -> dict:
    """Summarize medication logs, mood, and symptoms over seven days."""
    at = now()
    taken = 0
    scheduled = 0

    with db() as con:
        person_row = _person(con, person)

        for offset in range(7):
            day = at - timedelta(days=offset)

            for row in _day_rows(con, person_row, day, at):
                if row["status"] in ("upcoming", "due"):
                    continue

                scheduled += 1

                if row["status"] == "taken":
                    taken += 1

        since = (
            at - timedelta(days=7)
        ).isoformat(timespec="seconds")

        moods = [
            row["mood"]
            for row in con.execute(
                """
                SELECT mood FROM checkins
                WHERE person_id = ? AND logged_at >= ?
                ORDER BY logged_at
                """,
                (person_row["id"], since),
            )
        ]

        symptoms = [
            row["symptoms"]
            for row in con.execute(
                """
                SELECT symptoms FROM checkins
                WHERE person_id = ?
                  AND logged_at >= ?
                  AND symptoms != ''
                """,
                (person_row["id"], since),
            )
        ]

    percentage = (
        round(100 * taken / scheduled)
        if scheduled
        else None
    )

    average_mood = (
        round(sum(moods) / len(moods), 1)
        if moods
        else None
    )

    dose_text = (
        f"This week {person_row['name']} took "
        f"{taken} of {scheduled} doses"
    )

    if percentage is not None:
        dose_text += f", {percentage} percent."
    else:
        dose_text += "."

    parts = [dose_text]

    if average_mood is not None:
        trend = ""

        if len(moods) >= 4:
            half = len(moods) // 2

            earlier_average = (
                sum(moods[:half]) / half
            )

            later_moods = moods[half:]
            later_average = (
                sum(later_moods) / len(later_moods)
            )

            difference = later_average - earlier_average

            if difference > 0.5:
                trend = " and trending up"
            elif difference < -0.5:
                trend = " and trending down"

        parts.append(
            f"Average mood was {average_mood} out of 5{trend}."
        )

    if symptoms:
        unique_symptoms = sorted(set(symptoms))
        parts.append(
            f"Symptoms mentioned: {', '.join(unique_symptoms)}."
        )

    return {
        "speech": " ".join(parts),
        "person": person_row["name"],
        "doses_taken": taken,
        "doses_scheduled": scheduled,
        "adherence_percent": percentage,
        "average_mood": average_mood,
        "mood_entries": len(moods),
        "symptoms": sorted(set(symptoms)),
    }


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

def overview() -> dict:
    """Return all people, their schedules, and their latest check-ins."""
    at = now()
    output = []

    with db() as con:
        people = con.execute(
            "SELECT * FROM persons ORDER BY name"
        )

        for person_row in people:
            rows = _day_rows(con, person_row, at, at)

            for row in rows:
                row.pop("_med_id", None)

            last_checkin = con.execute(
                """
                SELECT mood, symptoms, note, logged_at
                FROM checkins
                WHERE person_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (person_row["id"],),
            ).fetchone()

            output.append({
                "name": person_row["name"],
                "relationship": person_row["relationship"],
                "doses": rows,
                "last_checkin": (
                    dict(last_checkin)
                    if last_checkin
                    else None
                ),
            })

    return {
        "now": at.isoformat(timespec="minutes"),
        "people": output,
    }
