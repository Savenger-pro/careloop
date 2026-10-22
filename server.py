"""CareLoop MCP server (Streamable HTTP) for Alexa+.

Run:  python server.py            -> http://127.0.0.1:8000/mcp  (MCP endpoint)
                                     http://127.0.0.1:8000/     (live dashboard)
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

import core

mcp = MCPServer(
    name="CareLoop",
    title="CareLoop: voice-first family caregiving",
    version="1.0.0",
    instructions=(
        "CareLoop helps a family caregiver look after elderly or unwell relatives by voice. "
        "Use it to add people and medications, log doses, ask what is due or missed, record "
        "mood check-ins and get a weekly summary. Replies include a short `speech` field that "
        "is safe to read aloud: prefer it over reading raw data. CareLoop never gives medical "
        "advice, never suggests changing a dose, and points the caregiver to a doctor or "
        "pharmacist when something looks wrong."
    ),
)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except core.CareError as e:
        raise ToolError(str(e))


@mcp.tool()
def add_person(name: str, relationship: str = "") -> dict:
    """Add someone to the care circle, e.g. name='Nani', relationship='grandmother'."""
    return _guard(core.add_person, name, relationship)


@mcp.tool()
def add_medication(person: str, medication: str, times: list[str], dose: str = "", notes: str = "") -> dict:
    """Schedule a medication. `times` are 24-hour HH:MM strings, e.g. ['08:00', '20:00']."""
    return _guard(core.add_medication, person, medication, times, dose, notes)


@mcp.tool()
def remove_medication(person: str, medication: str) -> dict:
    """Stop tracking a medication for a person."""
    return _guard(core.remove_medication, person, medication)


@mcp.tool()
def today_schedule(person: str) -> dict:
    """What has this person taken today, and what is still due? Includes overdue doses."""
    return _guard(core.today_schedule, person)


@mcp.tool()
def log_dose(person: str, medication: str, taken: bool = True, note: str = "") -> dict:
    """Record that a person took (or skipped, taken=false) a medication. Matches the nearest open slot today."""
    return _guard(core.log_dose, person, medication, taken, note)


@mcp.tool()
def missed_doses(person: str, days: int = 1) -> dict:
    """List doses that were not logged within the grace period, for today or the last N days."""
    return _guard(core.missed_doses, person, max(1, min(days, 14)))


@mcp.tool()
def log_checkin(person: str, mood: int, symptoms: str = "", note: str = "") -> dict:
    """Record a wellness check-in. mood is 1 (very low) to 5 (great). symptoms is free text."""
    return _guard(core.log_checkin, person, mood, symptoms, note)


@mcp.tool()
def weekly_summary(person: str) -> dict:
    """Seven-day summary: dose adherence, average mood and trend, symptoms mentioned."""
    return _guard(core.weekly_summary, person)


@mcp.prompt()
def morning_briefing(person: str) -> str:
    """A short spoken morning briefing for one person."""
    return (f"Give me a brief spoken morning update for {person}: call today_schedule, then missed_doses, "
            "and finish with one sentence on how they are doing. Keep it under 30 seconds when read aloud.")


# ---------------------------------------------------------------- dashboard (demo UI)
DASH = Path(__file__).with_name("dashboard.html")


@mcp.custom_route("/", methods=["GET"])
async def dashboard(request: Request) -> HTMLResponse:
    return HTMLResponse(DASH.read_text(encoding="utf-8"))


@mcp.custom_route("/api/overview", methods=["GET"])
async def api_overview(request: Request) -> JSONResponse:
    return JSONResponse(core.overview())


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(mcp.streamable_http_app(host=host), host=host, port=port)
