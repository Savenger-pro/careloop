# CareLoop: Submission Plan (solo, Alexa+ track)

**Deadline:** Oct 23, 2026, 12:00 PM PT = **Oct 24, 1:00 AM Bangladesh time**. Submit by Oct 23 evening BD time, don't wait for the last hour.

## Timeline (Bangladesh time)

| When | Do this |
| --- | --- |
| Oct 21 night | Devpost e register + Alexa+ track select. Project run koro (`python server.py`), `demo_client.py` chalao. GitHub repo banao, push koro |
| Oct 22 din | Public HTTPS URL (tunnel/deploy), Alexa+ theke connect kore real test. Jodi Alexa+ preview access na thake, **simulated Alexa+ web app path** nao (rules e allowed) |
| Oct 22 rat | Demo video record + YouTube e upload (public, English, under 3 min) |
| Oct 23 din | Devpost form fill: description, repo link, video, product feedback. Collaborator add (private repo hole) |
| Oct 23 evening | Final submit. Deadline er onek age |

## Submission checklist (from the official Devpost page)

- [ ] Text description: what it does + how it works
- [ ] GitHub repo with all source + run instructions (`README.md` ready). Public + open source license (`LICENSE` ready) **OR** private + collaborators: `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`, `emersonsklar` (invite 7 din e expire, submit er shomoy add koro)
- [ ] Repo must actually use MCP in code (`server.py` imports `MCPServer`, good)
- [ ] Demo video, **under 3 minutes**, YouTube/Vimeo, public, English, no copyrighted music
- [ ] Product feedback on every tool/SDK you used (MCP SDK, Alexa+ docs, Devpost resources)
- [ ] Track select: Alexa+
- [ ] Optional: friction log (up to 10% judging bonus). Kaj korar shomoy je jhamela hoy shob note rakho: task, steps, expected vs actual, workaround
- [ ] Optional extra: Open Source mini challenge (MIT licensed repo ready). Rules e check koro eta same project e apply hoy kina

## Demo video script (about 2:30)

1. **0:00 to 0:20, the problem.** "My grandmother lives two hours away. Did she take her pills? I never know."
2. **0:20 to 0:50, add medicine by voice.** Alexa+ ke bolo: add Nani's Metformin 8 AM and 8 PM. Dashboard e card show hobe.
3. **0:50 to 1:25, log + check-in.** "Nani just took her Metformin." Dashboard e status "taken" hoye jabe live. Tarpor mood check-in with a symptom.
4. **1:25 to 1:55, missed doses.** "What is Dadu missing today?" Alexa+ spoken answer + safety line (ask a doctor).
5. **1:55 to 2:20, weekly summary.** Seeded data diye: adherence, mood trend down for Dadu.
6. **2:20 to 2:45, tech + impact.** MCP server, Streamable HTTP, 8 tools, `speech` field for voice. Roadmap: proactive nudges, multi-caregiver.

Tip: `python seed_demo.py` age chalao, tahole weekly summary te real data thake. Judges prothom 3 minute ei dekhbe, tai best part ta shurute rakho.

## Judging criteria vs CareLoop

- **Tech implementation:** real MCP server, Streamable HTTP, 8 typed tools, prompt, tests via real MCP client
- **Design:** voice-first replies (short `speech`), live dashboard
- **Potential impact:** caregiving for elders, real daily problem, clear path beyond the hackathon
- **Quality of the idea:** Alexa+ er multi-device, always-in-the-home nature caregiving er jonno natural fit

## Product feedback template (Devpost form)

For each tool (MCP Python SDK, Alexa+ MCP integration, docs):
- What I used it for:
- What worked well:
- What needs work:
- How onboarding felt:
- Would I build with it again:

## Honest notes

- Ami (Claude) Alexa+ er actual device/preview registration step ta test korte pari nai. Official Resources page follow koro. Server ta standard MCP, Streamable HTTP, tai ota te connect hobe.
- Public deploy e authentication add korbe (OAuth). Shudhu demo er jonno tunnel thik ache.
- Eta medical device na. Server dose suggest kore na, shudhu mone koriye dey.
