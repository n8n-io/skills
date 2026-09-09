---
name: conversation-use-cases
description: "Use when you want to identify the intents and interaction patterns in how you work with coding agents (Claude Code, Codex, Cursor, OpenCode, Pi, Gemini CLI and others): what you ask for, how you steer and correct, how you check status, how you track the agent's work and your own, which integrations you use, and where a UI would beat chat. Also for a team collecting this from several people to design agent interfaces."
---

# Conversation Use-Cases

Produces a one-page report from the agent history already on the machine: the intents behind the asks, the interaction patterns as counts, the integrations, where chat fails, and ranked use-cases where UI would beat text. Message text never enters the report; intents are described in the report's own words, one short line each, so the report carries context without carrying conversations. The person's interview answers are the only verbatim text.

Why this shape: people will share how they work with agents, not what they said to them. A report with quotes does not get posted; a report with only numbers cannot be read. Paraphrased intent is the middle.

## Steps

1. **Discover stores.** From this skill's directory run `python3 scripts/session_miner.py --self-test` (must print `self-test ok`), then `python3 scripts/session_miner.py --discover`: it lists the agent stores on this machine and which are parsed (Claude Code, Codex, Cursor, OpenCode; Pi, Droid, Gemini CLI, Amp, Copilot CLI, Goose and Hermes when present) versus detected only. Fill section 0 from it plus the report's "Sessions by harness" table: one row per store, sessions parsed or "detected only", and the window from the Scope table (first session start to last session end).
2. **Count.** `python3 scripts/session_miner.py --since-days 60 --out ./conversation-use-cases` writes `session_miner_report.md` and `session_miner_output.json`. Read the report. If Cursor is present, run once more with `--no-cursor` and compare: Cursor sessions driven by orchestration tools (Orca, automations) record programmatic prompts as human turns and can dominate the counts; say which run each number comes from. Never open a transcript or database yourself; files reach 30 MB and most tool volume sits in subagent folders the script already walks. `--since-days` selects files by modification time (Cursor and OpenCode by last update), so a long-lived session can start before the window; say so when the Scope table shows it. Read the "Signals measured per harness" table before quoting any number: `not measured`, `store absent` and `skipped by flag` are not zero.
3. **Read intents, not sentences.** From `sessions` in the JSON take the 6 most recent with 10 or more `user_turns`. For each, `python3 scripts/session_miner.py --user-turns <session_id>` streams that session's human turns to stdout, secret-shaped strings redacted, nothing saved. For every ask category in the report write one line describing the typical intent in your own words (for example "wants to know what is still missing after a long autonomous run", "hands a bulleted QA list with screenshots and expects each item addressed"). Never copy a sentence, never name a person or a customer.
4. **Interview.** Section 8 of `references/report-template.md`, with AskUserQuestion, at most four questions per call. On an agent without AskUserQuestion (Codex, Cursor, OpenCode and others), ask the same questions in chat, four at a time, each with lettered options and a free-text line, and wait for the answer before the next batch. Order: 8a core (five), 8b issues and concerns (five), then the 8c cards from `references/use-cases.md` whose Gate fires in this person's report. Skip cards with a zero gate; they are marked "not asked". Per card: Fit with options fits, sometimes, no; then one free-text question covering what it must show and what you would click, skipped when Fit is no. Seed options from the person's own numbers (their top ask categories, their MCP servers, their counts) so most answers are one click; free text is always available. AskUserQuestion allows four options per question. When the evidence lists more than four candidates, split the question into part 1 and part 2 with the same stem and four options each, so the person can click instead of typing what the miner already found. Target under 15 minutes. Record the chosen option plus any free text verbatim. Never infer an answer; an unanswered question stays empty.
5. **Fill the template** into `./conversation-use-cases/conversation-use-cases-<YYYY-MM-DD>.md`. Every REQUIRED slot gets a value or `not measured` with one line saying why. Take counts from `session_miner_output.json` when a report table is cut (tool usage shows the top 25; the "Tracking and hand-off tools" table lists the tracking tools in full). Copy no project labels, session ids or paths from the report or the JSON; the template carries counts, categories and your one-line intents only. Section 7 takes the cards from `references/use-cases.md` and ranks them by the rule in the template: evidence count weighted by the 8c Fit answer (fits 2, sometimes 1, no 0); cards not asked rank by evidence alone and say so.
6. **Gate, then hand over.** Tick the four checks at the end of the template, delete any temporary file you created, give the person the path and the sharing note. They decide whether it leaves the machine.
7. **Draft the hand-over, never send it.** If a Slack drafting tool is available (for example `slack_send_message_draft` with `slack_search_users`), look up Filipe Tavares (filipe.tavares@n8n.io), create a draft DM with the sharing note and sections 6, 7 and 8 of the report pasted in, and tell the person: the draft exists, here is the link to it, attach the report file and adjust anything before sending. Never call a send tool. If no Slack tool is available, tell the person to DM the report file to Filipe Tavares on Slack with the sharing note, and print the note for them to copy.

## What a use-case looks like

| Field | Meaning |
|---|---|
| Intent | The recurring ask it serves, in your words |
| Trigger | The moment in a session where it would appear |
| Shows | What the UI puts on screen instead of prose |
| You can | The direct actions available on it |
| Evidence | The report metric and count behind it |
| Gate | The metric condition that makes the interview ask about it |
| Beats text because | One sentence |

Seed list: the twelve cards in `references/use-cases.md`, each with trigger, components, interactions, evidence metric and gate. Confirm or refute them with this person's numbers and answers; add a card only when the report shows a moment none of the twelve covers.

## Where each report section comes from

| Section | Source in `session_miner_report.md` |
|---|---|
| Intents | "What the human turns ask for" table, plus your one-line intent per category from step 3 |
| Steering and feedback | Feedback signals, Feedback batches, Steering, message length, pasted images |
| Agent behavior | "Agent behaviors" table: done claims, done then probe, prose vs structured questions, blocked on user, retractions, options offered, long replies, retries after error, runs over 2 minutes |
| Tracking the agent's work | "Tracking and hand-off tools" table: TaskCreate, TaskUpdate, ScheduleWakeup, Monitor, PushNotification, AskUserQuestion |
| Tracking own work | PR links, Artifact tool by action, SendUserFile in the tracking table, drafts and sends columns of the MCP servers table |
| Integrations | MCP servers with reads and writes, Skill invocations, Bash leading words and process probes, permission modes, models |
| Waiting | active vs wall-clock minutes, turn gaps, longest gap, resumptions and "What I ask when I come back", runs over 2 minutes, hours of day |
| Delegation | Agent dispatches, parallel fan-out, subagent tool calls |
| Use-case gates | The Gate column of `references/use-cases.md`, checked against the same report |

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
| Offering four options when the evidence lists eight | Split into part 1 and part 2 with the same stem; the person clicks what the miner found. |
| Sending the Slack message instead of drafting it | Draft only, give the link, the person sends. |
| Asking every card regardless of the gate | Ask only cards whose gate fires. The rest are "not asked" and rank by evidence alone. |
| Calling a tool zero because it is not in the top-25 table | Use the "Tracking and hand-off tools" table or the JSON `tools` map; the top 25 is a cut. |
| Copying project labels, session ids or paths into the template | Counts and categories only; the raw report and JSON stay on the machine. |
| Summing ask categories as if they were distinct turns | One turn can hit several categories; use "also matched" for gates, primary for the intents table. |

## Sharing note

The person posts this; the agent drafts at most, and never sends.

> Ran `/conversation-use-cases` on my machine: the intents behind how I work with coding agents, how I steer and check on them, which integrations I use, and where a UI would beat chat for me. Counts and one-line intents only, no message text. Report attached.
