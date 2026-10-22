"""CareLoop core logic: people, medications, dose logs, check-ins.

Pure Python + SQLite so it is easy to test and has no extra dependencies.
Every public function returns a dict with a short `speech` string (written
to be read aloud by Alexa+) plus structured data.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get("CARELOOP_DB", os.path.join(os.path.dirname(__file__), "careloop.db"))
TZ = ZoneInfo(os.environ.get("CARELOOP_TZ", "Asia/Dhaka"))
GRACE_MINUTES = int(os.environ.get("CARELOOP_GRACE_MIN", "60"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE NOT NULL, relationship TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS meds(
  id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES persons(id),
  name TEXT NOT NULL COLLATE NOCASE, dose TEXT DEFAULT '', times TEXT NOT NULL,
  notes TEXT DEFAULT '', active INTEGER DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS dose_logs(
  id INTEGER PRIMARY KEY, med_id INTEGER NOT NULL REFERENCES meds(id),
  slot TEXT NOT NULL, taken INTEGER NOT NULL, logged_at TEXT NOT NULL, note TEXT DEFAULT '',
  UNIQUE(med_id, slot));
CREATE TABLE IF NOT EXISTS checkins(
  id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES persons(id),
  mood INTEGER NOT NULL, symptoms TEXT DEFAULT '', note TEXT DEFAULT '', logged_at TEXT NOT NULL);
"""


def now() -> datetime:
    override = os.environ.get("CARELOOP_NOW")  # used by tests/demo seeding
    if override:
        return datetime.fromisoformat(override).replace(tzinfo=TZ)
    return datetime.now(TZ)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    cols = [r["name"] for r in con.execute("PRAGMA table_info(meds)")]
    if "created_at" not in cols:  # migrate older DBs
        con.execute("ALTER TABLE meds ADD COLUMN created_at TEXT")
    return con


class CareError(ValueError):
    """User-facing error (bad name, bad time...)."""


def _person(con, name: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM persons WHERE name = ?", (name.strip(),)).fetchone()
    if not row:
        known = [r["name"] for r in con.execute("SELECT name FROM persons ORDER BY name")]
        hint = f" I know: {', '.join(known)}." if known else " Add them first."
        raise CareError(f"I don't have anyone called {name}.{hint}")
    return row


def _meds_for(con, person_id: int, name: str | None = None):
    q, args = "SELECT * FROM meds WHERE person_id=? AND active=1", [person_id]
    if name:
        q += " AND name = ?"
        args.append(name.strip())
    return con.execute(q + " ORDER BY name", args).fetchall()


def _parse_times(times: list[str]) -> list[str]:
    out = []
    for t in times:
        try:
            h, m = t.strip().split(":")
            out.append(f"{int(h):02d}:{int(m):02d}")
            datetime.strptime(out[-1], "%H:%M")
        except Exception:
            raise CareError(f"'{t}' is not a valid time. Use 24-hour HH:MM like 08:00 or 20:30.")
    if not out:
        raise CareError("Give at least one time, like 08:00.")
    return sorted(set(out))


def _spoken_time(hhmm: str) -> str:
    return datetime.strptime(hhmm, "%H:%M").strftime("%-I:%M %p").replace(":00", "")


# ---------------------------------------------------------------- people / meds
def add_person(name: str, relationship: str = "") -> dict:
    with db() as con:
        try:
            con.execute("INSERT INTO persons(name, relationship) VALUES (?,?)", (name.strip(), relationship))
        except sqlite3.IntegrityError:
            raise CareError(f"{name} is already in your care circle.")
    return {"speech": f"Added {name} to your care circle.", "name": name, "relationship": relationship}


def add_medication(person: str, medication: str, times: list[str], dose: str = "", notes: str = "",
                   start: datetime | None = None) -> dict:
    times = _parse_times(times)
    with db() as con:
        p = _person(con, person)
        if _meds_for(con, p["id"], medication):
            raise CareError(f"{p['name']} already has {medication}. Remove it first to change the times.")
        con.execute(
            "INSERT INTO meds(person_id,name,dose,times,notes,created_at) VALUES (?,?,?,?,?,?)",
            (p["id"], medication.strip(), dose, json.dumps(times), notes,
             (start or now()).isoformat(timespec="seconds")),
        )
    spoken = " and ".join(_spoken_time(t) for t in times)
    return {"speech": f"Okay. {p['name']} will take {medication} at {spoken}.",
            "person": p["name"], "medication": medication, "dose": dose, "times": times}


def remove_medication(person: str, medication: str) -> dict:
    with db() as con:
        p = _person(con, person)
        cur = con.execute("UPDATE meds SET active=0 WHERE person_id=? AND name=? AND active=1", (p["id"], medication.strip()))
        if not cur.rowcount:
            raise CareError(f"{p['name']} isn't taking {medication}.")
    return {"speech": f"Removed {medication} for {p['name']}."}


# ---------------------------------------------------------------- schedule
def _slots_for_day(med: sqlite3.Row, day: datetime):
    for t in json.loads(med["times"]):
        h, m = map(int, t.split(":"))
        yield day.replace(hour=h, minute=m, second=0, microsecond=0)


def _status(slot: datetime, log: sqlite3.Row | None, at: datetime) -> str:
    if log is not None:
        return "taken" if log["taken"] else "skipped"
    if at > slot + timedelta(minutes=GRACE_MINUTES):
        return "missed"
    return "due" if at >= slot - timedelta(minutes=30) else "upcoming"


def _day_rows(con, person: sqlite3.Row, day: datetime, at: datetime):
    rows = []
    for med in _meds_for(con, person["id"]):
        started = datetime.fromisoformat(med["created_at"]) if med["created_at"] else None
        for slot in _slots_for_day(med, day):
            if started and slot < started.replace(hour=0, minute=0, second=0):
                continue
            key = slot.strftime("%Y-%m-%d %H:%M")
            log = con.execute("SELECT * FROM dose_logs WHERE med_id=? AND slot=?", (med["id"], key)).fetchone()
            rows.append({"medication": med["name"], "dose": med["dose"], "time": slot.strftime("%H:%M"),
                         "slot": key, "status": _status(slot, log, at), "note": log["note"] if log else "",
                         "_med_id": med["id"]})
    return sorted(rows, key=lambda r: (r["time"], r["medication"]))


def today_schedule(person: str) -> dict:
    at = now()
    with db() as con:
        p = _person(con, person)
        rows = _day_rows(con, p, at, at)
    for r in rows:
        r.pop("_med_id")
    if not rows:
        return {"speech": f"{p['name']} has no medications scheduled.", "person": p["name"], "doses": []}
    pending = [r for r in rows if r["status"] in ("due", "upcoming", "missed")]
    if not pending:
        speech = f"All done. {p['name']} has finished every dose for today."
    else:
        nxt = pending[0]
        speech = (f"{p['name']} has {len(pending)} dose{'s' if len(pending) != 1 else ''} left today. "
                  f"Next is {nxt['medication']} at {_spoken_time(nxt['time'])}"
                  + (", which is overdue." if nxt["status"] == "missed" else "."))
    return {"speech": speech, "person": p["name"], "date": at.strftime("%Y-%m-%d"), "doses": rows}


def log_dose(person: str, medication: str, taken: bool = True, note: str = "") -> dict:
    """Record a dose for the closest scheduled slot today that has no log yet."""
    at = now()
    with db() as con:
        p = _person(con, person)
        meds = _meds_for(con, p["id"], medication)
        if not meds:
            raise CareError(f"{p['name']} isn't taking {medication}.")
        open_rows = [r for r in _day_rows(con, p, at, at) if r["_med_id"] == meds[0]["id"] and r["status"] != "taken" and r["status"] != "skipped"]
        if not open_rows:
            return {"speech": f"{medication} is already logged for every slot today.", "already_logged": True}
        # A caregiver saying "she took it" almost always means the dose that is due or overdue
        # (the most recent one), not one hours away. Fall back to the soonest upcoming slot.
        overdue = [r for r in open_rows if r["status"] in ("due", "missed")]
        target = max(overdue, key=lambda r: r["slot"]) if overdue else min(open_rows, key=lambda r: r["slot"])
        con.execute("INSERT INTO dose_logs(med_id,slot,taken,logged_at,note) VALUES (?,?,?,?,?)",
                    (target["_med_id"], target["slot"], int(taken), at.isoformat(timespec="seconds"), note))
    verb = "Logged" if taken else "Marked as skipped:"
    return {"speech": f"{verb} {medication} for {p['name']}, {_spoken_time(target['time'])} dose.",
            "person": p["name"], "medication": medication, "slot": target["slot"], "taken": taken}


def missed_doses(person: str, days: int = 1) -> dict:
    at = now()
    missed = []
    with db() as con:
        p = _person(con, person)
        for d in range(days):
            day = at - timedelta(days=d)
            missed += [r for r in _day_rows(con, p, day, at) if r["status"] == "missed"]
    for r in missed:
        r.pop("_med_id")
    if not missed:
        return {"speech": f"No missed doses for {p['name']}.", "person": p["name"], "missed": []}
    names = ", ".join(sorted({m["medication"] for m in missed}))
    return {"speech": f"{p['name']} missed {len(missed)} dose{'s' if len(missed) != 1 else ''}: {names}. "
                      "Please check in with them and, if you're unsure what to do, ask their doctor or pharmacist.",
            "person": p["name"], "missed": missed}


# ---------------------------------------------------------------- check-ins / summary
def log_checkin(person: str, mood: int, symptoms: str = "", note: str = "") -> dict:
    if not 1 <= mood <= 5:
        raise CareError("Mood must be a number from 1 (very low) to 5 (great).")
    at = now()
    with db() as con:
        p = _person(con, person)
        con.execute("INSERT INTO checkins(person_id,mood,symptoms,note,logged_at) VALUES (?,?,?,?,?)",
                    (p["id"], mood, symptoms, note, at.isoformat(timespec="seconds")))
    speech = f"Noted. {p['name']}'s mood is {mood} out of 5."
    if mood <= 2 or symptoms:
        speech += " Keep an eye on them, and contact a doctor if you're worried."
    return {"speech": speech, "person": p["name"], "mood": mood, "symptoms": symptoms}


def weekly_summary(person: str) -> dict:
    at = now()
    taken = scheduled = 0
    with db() as con:
        p = _person(con, person)
        for d in range(7):
            for r in _day_rows(con, p, at - timedelta(days=d), at):
                if r["status"] in ("upcoming", "due"):
                    continue
                scheduled += 1
                taken += r["status"] == "taken"
        since = (at - timedelta(days=7)).isoformat(timespec="seconds")
        moods = [r["mood"] for r in con.execute(
            "SELECT mood FROM checkins WHERE person_id=? AND logged_at>=? ORDER BY logged_at", (p["id"], since))]
        symptoms = [r["symptoms"] for r in con.execute(
            "SELECT symptoms FROM checkins WHERE person_id=? AND logged_at>=? AND symptoms!=''", (p["id"], since))]
    pct = round(100 * taken / scheduled) if scheduled else None
    avg = round(sum(moods) / len(moods), 1) if moods else None
    parts = [f"This week {p['name']} took {taken} of {scheduled} doses" + (f", {pct} percent." if pct is not None else ".")]
    if avg is not None:
        trend = ""
        if len(moods) >= 4:
            half = len(moods) // 2
            diff = sum(moods[half:]) / len(moods[half:]) - sum(moods[:half]) / half
            trend = " and trending up" if diff > 0.5 else " and trending down" if diff < -0.5 else ""
        parts.append(f"Average mood was {avg} out of 5{trend}.")
    if symptoms:
        parts.append(f"Symptoms mentioned: {', '.join(sorted(set(symptoms)))}.")
    return {"speech": " ".join(parts), "person": p["name"], "doses_taken": taken, "doses_scheduled": scheduled,
            "adherence_percent": pct, "average_mood": avg, "mood_entries": len(moods), "symptoms": sorted(set(symptoms))}


# ---------------------------------------------------------------- dashboard
def overview() -> dict:
    at = now()
    out = []
    with db() as con:
        for p in con.execute("SELECT * FROM persons ORDER BY name"):
            rows = _day_rows(con, p, at, at)
            for r in rows:
                r.pop("_med_id")
            last = con.execute("SELECT mood, symptoms, note, logged_at FROM checkins WHERE person_id=? ORDER BY id DESC LIMIT 1", (p["id"],)).fetchone()
            out.append({"name": p["name"], "relationship": p["relationship"], "doses": rows,
                        "last_checkin": dict(last) if last else None})
    return {"now": at.isoformat(timespec="minutes"), "people": out}
