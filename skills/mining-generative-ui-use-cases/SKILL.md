---
name: mining-generative-ui-use-cases
description: Use when you want to find where generative UI would help, based on how you actually work with coding agents (Claude Code, Codex, Cursor, OpenCode): what you ask them, how you steer and correct them, how you check status, how you track their work and yours, which integrations you use. Also for a team collecting this from several people to design agent interfaces.
---

# Mining Generative UI Use-Cases

Produces a one-page report from the agent history already on the machine: interaction patterns as counts, integrations, where chat fails, and ranked generative UI use-cases. No message text is read into the report, none leaves the machine. The script emits counts and categories only; the person's own interview answers are the only free text.

Why counts only: people will share how they work, not what they said. A report with quotes does not get posted.

## Steps

1. **Discover stores.** `python3 scripts/session_miner.py --discover` prints which agent stores exist (Claude Code and Codex are parsed; OpenCode, Cursor, Pi, Goose, Gemini CLI, Aider and others are detected and listed). Record the table in section 0 of the report.
2. **Count.** `python3 scripts/session_miner.py --since-days 60 --out ./genui-report` writes `session_miner_report.md` and `session_miner_output.json`. Read the report. Never open a transcript file yourself: they reach 30 MB and most tool volume sits in subagent folders the script already walks.
3. **Sample shapes, never sentences.** From `sessions` in the JSON take the 6 most recent with 10 or more `user_turns`. For each run `python3 scripts/session_miner.py --user-turns <session_id>`; it streams that session's human turns to stdout, secret-shaped strings redacted, nothing saved. Look only for shapes: how steering arrives mid-run, what a status ask looks like, how feedback is batched, what a hand-back looks like. Write down categories and counts. Do not write down a sentence you saw, not even paraphrased.
4. **Interview.** Ask the five questions in `references/report-template.md` with AskUserQuestion in one call. The answers go into the report verbatim; they are the person speaking about themselves.
5. **Fill the template** into `./genui-report/genui-use-cases-<YYYY-MM-DD>.md`. Every REQUIRED slot gets a value or `not measured` plus one line saying why. Rank use-cases by evidence count, highest first.
6. **Gate, then hand over.** Tick the four checks at the end of the template, delete any temporary file you created, give the person the path and the sharing note. They decide whether it leaves the machine.

## What a use-case looks like

| Field | Meaning |
|---|---|
| Trigger | The moment in a session where it would appear |
| Shows | What the UI puts on screen instead of prose |
| You can | The direct actions available on it |
| Evidence | The report metric and count that justify it |
| Beats text because | One sentence |

Seed list from a first study, to confirm or refute with this person's numbers: live run board for parallel agents; needs-you panel for human-only steps; verification board that splits done into implemented, wired, verified; decision form for batched questions; living plan or document with keep, cut and diff; screenshot walkthrough with pinned comments; feedback-batch triage table; outbound draft composer for Slack, email, PR text; step pipeline with per-step evidence for automations; long-run operation console; return-to-session brief.

## Where each report section comes from

| Section | Source in `session_miner_report.md` |
|---|---|
| Asks | "What the human turns ask for" table |
| Steering and feedback | Feedback signals, Steering, message length, pasted images |
| Tracking the agent's work | TaskCreate/TaskUpdate, ScheduleWakeup, Monitor, PushNotification, AskUserQuestion counts in tool usage |
| Tracking own work | PR links, Artifact publishes, SendUserFile, drafts vs sends in MCP servers |
| Integrations | MCP servers, Skill invocations, Bash leading words, permission modes |
| Waiting | active vs wall-clock minutes, turn gaps, longest gap, hours of day |
| Delegation | Agent dispatches, parallel fan-out, subagent tool calls |

## Mistakes seen in test runs

| Mistake | Fix |
|---|---|
| Quoting or paraphrasing a message | Categories and counts only. Only interview answers are free text. |
| Reading a JSONL directly "just to check" | The script has `--user-turns` for bounded reads and redacts on the way out. |
| Treating continuation summaries or resubmitted prompts as human turns | The script skips them; do not add them back from a read. |
| Guessing what a record type means | The script docstring documents `isMeta`, `origin.kind`, `promptSource`, `pr-link`, subagent folders. Unknown means `not measured`. |
| Inferring wishes from the data | Ask. A report that speaks for the person is not theirs. |
| Naming colleagues, customers, or other teams' repos | Roles and counts only. |
| Leaving extracted files behind | Delete before handover. |

## Sharing note

The person posts this; the agent never sends.

> Ran `/mining-generative-ui-use-cases` on my machine: how I work with coding agents (asks, steering, feedback, status checks, integrations) and where UI would beat chat for me. Counts only, no message text. Report attached.
