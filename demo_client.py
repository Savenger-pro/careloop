"""Talks to a running CareLoop server over Streamable HTTP, like Alexa+ would.

    python demo_client.py [http://127.0.0.1:8000/mcp]

Useful for (1) smoke-testing before you submit and (2) a terminal shot in the demo video.
"""
import asyncio
import json
import sys

from mcp.client import Client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"

STEPS = [
    ("add_person", {"name": "Nani", "relationship": "grandmother"}),
    ("add_medication", {"person": "Nani", "medication": "Metformin", "dose": "500 mg", "times": ["08:00", "20:00"]}),
    ("add_medication", {"person": "Nani", "medication": "Vitamin D", "dose": "1 tablet", "times": ["13:00"]}),
    ("today_schedule", {"person": "Nani"}),
    ("log_dose", {"person": "Nani", "medication": "Metformin"}),
    ("log_checkin", {"person": "Nani", "mood": 4, "symptoms": "mild headache"}),
    ("missed_doses", {"person": "Nani"}),
    ("weekly_summary", {"person": "Nani"}),
    ("log_dose", {"person": "Rahim", "medication": "Aspirin"}),  # error path
]


def payload(result):
    if result.structured_content:
        return result.structured_content
    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except ValueError:
        return {"text": text}


async def main():
    async with Client(URL) as client:
        tools = await client.list_tools()
        print("Tools:", ", ".join(t.name for t in tools.tools), "\n")
        for name, args in STEPS:
            res = await client.call_tool(name, args)
            data = payload(res)
            tag = "ERROR" if res.is_error else "ok"
            print(f"> {name}({json.dumps(args)})  [{tag}]")
            print("  Alexa+ says:", data.get("speech") or data.get("text"), "\n")


asyncio.run(main())
