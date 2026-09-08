---
name: conversation-use-cases
description: Use when you want to identify the intents and interaction patterns in how you work with coding agents (Claude Code, Codex, Cursor, OpenCode, Pi, Gemini CLI and others): what you ask for, how you steer and correct, how you check status, how you track the agent's work and your own, which integrations you use, and where a UI would beat chat. Also for a team collecting this from several people to design agent interfaces.
---

# Conversation Use-Cases

Produces a one-page report from the agent history already on the machine: the intents behind the asks, the interaction patterns as counts, the integrations, where chat fails, and ranked use-cases where UI would beat text. Message text never enters the report; intents are described in the report's own words, one short line each, so the report carries context without carrying conversations. The person's interview answers are the only verbatim text.

Why this shape: people will share how they work with agents, not what they said to them. A report with quotes does not get posted; a report with only numbers cannot be read. Paraphrased intent is the middle.

## Steps

1. **Discover stores.** `python3 scripts/session_miner.py --discover` lists the agent stores on this machine and which are parsed (Claude Code, Codex, Cursor, OpenCode; Pi, Droid, Gemini CLI, Amp, Copilot CLI, Goose and Hermes when present) versus detected only. Copy the table into section 0.
2. **Count.** `python3 scripts/session_miner.py --since-days 60 --out ./conversation-use-cases` writes `session_miner_report.md` and `session_miner_output.json`. Read the report. If Cursor is present, run once more with `--no-cursor` and compare: Cursor sessions driven by orchestration tools (Orca, automations) record programmatic prompts as human turns and can dominate the counts; say which run each number comes from. Never open a transcript or database yourself; files reach 30 MB and most tool volume sits in subagent folders the script already walks.
3. **Read intents, not sentences.** From `sessions` in the JSON take the 6 most recent with 10 or more `user_turns`. For each, `python3 scripts/session_miner.py --user-turns <session_id>` streams that session's human turns to stdout, secret-shaped strings redacted, nothing saved. For every ask category in the report write one line describing the typical intent in your own words (for example "wants to know what is still missing after a long autonomous run", "hands a bulleted QA list with screenshots and expects each item addressed"). Never copy a sentence, never name a person or a customer.
4. **Interview.** Ask the five questions in `references/report-template.md` with AskUserQuestion, four in the first call and one in the second (the tool takes at most four per call). Offer options drawn from the person's own numbers so answering is fast; free text is always available. Their answers go in verbatim; they are the person speaking about themselves.
5. **Fill the template** into `./conversation-use-cases/conversation-use-cases-<YYYY-MM-DD>.md`. Every REQUIRED slot gets a value or `not measured` with one line saying why. Rank use-cases by evidence count.
6. **Gate, then hand over.** Tick the four checks at the end of the template, delete any temporary file you created, give the person the path and the sharing note. They decide whether it leaves the machine.

## What a use-case looks like

| Field | Meaning |
|---|---|
| Intent | The recurring ask it serves, in your words |
| Trigger | The moment in a session where it would appear |
| Shows | What the UI puts on screen instead of prose |
| You can | The direct actions available on it |
| Evidence | The report metric and count behind it |
| Beats text because | One sentence |

Seed list from a first study, to confirm or refute with this person's numbers: live run board for parallel agents; needs-you panel for human-only steps; verification board that splits done into implemented, wired, verified; decision form for batched questions; living plan or document with keep, cut and diff; screenshot walkthrough with pinned comments; feedback-batch triage table; outbound draft composer for Slack, email and PR text; step pipeline with per-step evidence for automations; long-run operation console; return-to-session brief.

## Where each report section comes from

| Section | Source in `session_miner_report.md` |
|---|---|
| Intents | "What the human turns ask for" table, plus your one-line intent per category from step 3 |
| Steering and feedback | Feedback signals, Steering, message length, pasted images |
| Tracking the agent's work | TaskCreate, TaskUpdate, ScheduleWakeup, Monitor, PushNotification, AskUserQuestion in tool usage |
| Tracking own work | PR links, Artifact publishes, SendUserFile, drafts vs sends in MCP servers |
| Integrations | MCP servers, Skill invocations, Bash leading words, permission modes, models |
| Waiting | active vs wall-clock minutes, turn gaps, longest gap, hours of day |
| Delegation | Agent dispatches, parallel fan-out, subagent tool calls |

## Mistakes seen in test runs

| Mistake | Fix |
|---|---|
| Copying a sentence, even a short one | Describe the intent in your words. Only interview answers are verbatim. |
| Reading a JSONL or database directly "just to check" | `--user-turns` is the bounded, redacted read. |
| Counting continuation summaries or resubmitted prompts as human turns | The script skips them; do not add them back. |
| Guessing what a record type means | The script docstring covers `isMeta`, `origin.kind`, `promptSource`, `pr-link`, subagent folders, and each harness format. Unknown means `not measured`. |
| Inferring wishes from the data | Ask. A report that speaks for the person is not theirs. |
| Naming colleagues, customers, or other teams' repos | Roles and counts only. |
| Leaving extracted files behind | Delete before handover. |
| Treating orchestrated Cursor sessions as human interaction | Compare with `--no-cursor`; report both and say which you used. |

## Sharing note

The person posts this; the agent never sends.

> Ran `/conversation-use-cases` on my machine: the intents behind how I work with coding agents, how I steer and check on them, which integrations I use, and where a UI would beat chat for me. Counts and one-line intents only, no message text. Report attached.
