# CareLoop

**A voice-first caregiving assistant for Alexa+, built as a self-hosted MCP server.**

Millions of people look after an elderly parent or grandparent from another room, another city or another country. The hard part is not the medicine itself, it is the small questions that never stop: *Did Nani take her evening pills? Did anyone check on Dadu today? Is he getting better or worse this week?*

CareLoop lets a caregiver answer all of that just by talking to Alexa+:

> "Alexa, add Nani's Metformin, 500 milligrams, at 8 AM and 8 PM."
> "Alexa, Nani just took her Metformin."
> "Alexa, what is Dadu missing today?"
> "Alexa, how was Nani's week?"

## Alexa+ track

- Self-hosted **MCP server**, **Streamable HTTP** transport, current MCP spec (built with the official Python SDK `mcp` 2.x; protocol version `2026-07-28`, which is newer than the required `2025-11-25`).
- Endpoint: `POST /mcp`
- 8 tools, 1 prompt. Every tool returns a short `speech` string written to be read aloud, plus structured data.

| Tool | What it does |
| --- | --- |
| `add_person` | Add someone to the care circle |
| `add_medication` | Schedule a medication at one or more times |
| `remove_medication` | Stop tracking a medication |
| `today_schedule` | What is taken, due, upcoming or overdue today |
| `log_dose` | Mark a dose taken or skipped (matches the due or overdue slot) |
| `missed_doses` | Doses not logged within the grace period (today or last N days) |
| `log_checkin` | Mood 1 to 5 plus optional symptoms |
| `weekly_summary` | Adherence %, mood average and trend, symptoms mentioned |

Prompt: `morning_briefing` builds a spoken update from the tools above.

### Safety by design

CareLoop is a *memory aid*, not a medical device. It never recommends doses, never suggests changing a schedule, and always points to a doctor or pharmacist when doses are missed or symptoms are mentioned. These rules are in the server `instructions` so the agent follows them too.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python seed_demo.py          # optional: a believable week of history for demos
python server.py             # http://127.0.0.1:8000
```

- MCP endpoint: `http://127.0.0.1:8000/mcp`
- Live dashboard (auto-refreshes every 3 seconds): `http://127.0.0.1:8000/`
- Smoke test as a real MCP client: `python demo_client.py`

Environment variables: `HOST`, `PORT`, `CARELOOP_DB` (SQLite path), `CARELOOP_TZ` (default `Asia/Dhaka`), `CARELOOP_GRACE_MIN` (minutes before a dose counts as missed, default 60).

### Expose it to Alexa+

Alexa+ needs a public HTTPS URL. For a quick demo, tunnel your local server (for example with `cloudflared tunnel --url http://localhost:8000`) and register `https://<your-tunnel>/mcp` following the Alexa+ MCP integration steps linked from the hackathon Resources page. For anything beyond a demo, deploy behind HTTPS and add authentication (the SDK supports OAuth token verification).

## Project layout

```
server.py        MCP server (tools, prompt, dashboard routes)
core.py          All business logic + SQLite, no MCP imports, easy to test
dashboard.html   Live caregiver view
demo_client.py   MCP client that exercises every tool over Streamable HTTP
seed_demo.py     Demo data
```

## Roadmap

- Proactive nudges ("Nani's 8 PM dose is overdue") through Alexa+ routines
- Multiple caregivers sharing one circle, with per-person permissions
- Refill reminders and doctor-visit notes
- Bengali and Hindi voice phrasing

## License

MIT
