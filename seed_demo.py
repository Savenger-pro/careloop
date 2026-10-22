"""Fill a fresh database with a believable week of history for the demo video.

    python seed_demo.py          # seeds Nani + Dadu, six past days, today left open
    CARELOOP_DB=other.db python seed_demo.py

Today is deliberately left empty so you can log doses live (by voice) on camera.
"""
import os
from datetime import datetime, timedelta

import core

PLAN = {
    "Nani": ("grandmother", [("Metformin", "500 mg", ["08:00", "20:00"]), ("Vitamin D", "1 tablet", ["13:00"])]),
    "Dadu": ("grandfather", [("Amlodipine", "5 mg", ["09:00"]), ("Atorvastatin", "10 mg", ["21:00"])]),
}
# (day offset, med, slot time) that were forgotten, to make the summary interesting
MISSED = {("Nani", 4, "20:00"), ("Nani", 2, "08:00"), ("Dadu", 3, "21:00")}
MOODS = {"Nani": [3, 3, 4, 3, 4, 5], "Dadu": [4, 4, 3, 2, 2, 3]}
SYMPTOMS = {("Dadu", 3): "dizzy in the morning", ("Dadu", 2): "tired"}


def at(day: datetime, hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0).isoformat(timespec="seconds")


def main():
    real_now = datetime.now(core.TZ).replace(tzinfo=None)
    start = real_now - timedelta(days=6)
    os.environ["CARELOOP_NOW"] = at(start, "07:00")
    for name, (rel, meds) in PLAN.items():
        core.add_person(name, rel)
        for med, dose, times in meds:
            core.add_medication(name, med, times, dose, start=start.replace(tzinfo=core.TZ))

    for offset in range(6, 0, -1):
        day = real_now - timedelta(days=offset)
        for name, (_, meds) in PLAN.items():
            for med, _, times in meds:
                for t in times:
                    if (name, offset, t) in MISSED:
                        continue
                    os.environ["CARELOOP_NOW"] = at(day, t)
                    core.log_dose(name, med)
            os.environ["CARELOOP_NOW"] = at(day, "18:00")
            core.log_checkin(name, MOODS[name][6 - offset], SYMPTOMS.get((name, offset), ""))

    os.environ.pop("CARELOOP_NOW")
    print("Seeded:", ", ".join(PLAN), "| today is open for live logging.")


if __name__ == "__main__":
    main()
