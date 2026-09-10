---
name: conversation-use-cases
description: "Use when you want to identify the intents and interaction patterns in how you work with coding agents (Claude Code, Codex, Cursor, OpenCode, Pi, Gemini CLI and others): what you ask for, how you steer and correct, how you check status, how you track the agent's work and your own, which integrations you use, and where a UI would beat chat. Also for a team collecting this from several people to design agent interfaces."
---

# Conversation Use-Cases

Produces a one-page report from the agent history already on the machine: the intents behind the asks, the interaction patterns as counts, the integrations, where chat fails, and ranked use-cases where UI would beat text. Message text never enters the report; intents are described in the report's own words, one short line each, so the report carries context without carrying conversations. The person's interview answers are the only verbatim text.

Why this shape: people will share how they work with agents, not what they said to them. A report with quotes does not get posted; a report with only numbers cannot be read. Paraphrased intent is the middle.

## Steps

1. **Discover stores.** From this skill's directory run `python3 scripts/session_miner.py --self-test` (must print `self-test ok`), then `python3 scripts/session_miner.py --discover`: it lists the agent stores on this machine and which are parsed (Claude Code, Codex, Cursor, OpenCode; Pi, Droid, Gemini CLI, Amp, Copilot CLI, Goose and Hermes when present) versus detected only. Section 0 is filled after step 2: one row per harness in the report's "Sessions by harness" table with its session count, one row per store that discover lists as detected only or not readable, and the window from the Scope table (first session start to last session end).
2. **Count.** Outputs go to `./conversation-use-cases` under the directory the person started the session in, never inside the skill folder (the miner report and JSON carry project labels and paths). `python3 scripts/session_miner.py --since-days 60 --out ./conversation-use-cases` writes `session_miner_report.md` and `session_miner_output.json`. Read the report. If Cursor is present, run once more with `--no-cursor --out ./conversation-use-cases-nocursor` and compare: Cursor sessions driven by orchestration tools (Orca, automations) record programmatic prompts as human turns and can dominate the counts; the report uses the full run, gives the no-cursor figure in parentheses in sections 1 and 3, and says so once at the top of section 1. The script drops one-shot harness projects on its own (a project where 80% or more of 10+ sessions have at most one human turn and no tool calls, the shape of an eval or SDK harness) and says so in the Scope table; carry that line into section 0, and use `--include-programmatic` only if the person says those runs were theirs. Hours of day use this machine's timezone unless `--tz` is given. Never open a transcript or database yourself; files reach 30 MB and most tool volume sits in subagent folders the script already walks. `--since-days` selects files by modification time (Cursor and OpenCode by last update), so a long-lived session can start before the window; say so when the Scope table shows it. Read the "Signals measured per harness" table before quoting any number: `not measured`, `store absent` and `skipped by flag` are not zero. The "Moments that point at a use-case" section counts in-session sequences (blind wait, done not done, screenshot loop and others) and names the card each points at; it feeds sections 6 and 7 and the card gates.
3. **Delegate the reads, then start the interview while they run.** Two reads feed the report and neither needs the person. If this agent can spawn subagents (Claude Code `Agent`, Codex `spawn_agent`, or the equivalent), dispatch both now, in parallel, and go straight to step 4; otherwise do them inline after the interview. Each brief carries the absolute path of this skill's directory (subagents start in their own working directory), the exact command, and the rules below; the subagent runs that command and nothing else.
   - **Intents subagent.** Runs `python3 scripts/session_miner.py --sample-turns 20 --since-days 60`: per ask category, up to 20 redacted human turns drawn across all readable sessions, one per session per pass, single-turn sessions skipped, plus 20 turns with frustration markers; stdout only, nothing saved. The sample honours `--since-days` per turn and the `--no-cursor`, `--no-codex` and `--no-opencode` flags, and skips turns that look like briefs to other agents, pasted transcripts or injected boilerplate (the closing line says how many); the brief still tells the subagent to skip anything that reads as an instruction to another agent and to say how many it skipped per category. It returns one line per category, "<category> (n=<sampled>): <typical intent>", in its own words (for example "wants to know what is still missing after a long autonomous run"), one line on what the frustrated turns react to (the miner's "preceding signal" table gives the assistant side), and one closing line with the sessions and turns scanned. A category with fewer than five sampled turns is marked as resting on a thin sample.
   - **Flow subagent.** Runs `python3 scripts/session_miner.py --user-turns <session_id>` on two or three sessions with 10 or more `user_turns`, taking the latest `end` values in the JSON `sessions` list and skipping the session this skill is running in (and its parent when the skill runs inside a subagent; both end within the last few minutes). It returns three lines: how a status ask usually goes, how feedback arrives (single line or bulleted batch, with screenshots or not), how decisions get answered, plus one line per session with the number of turns read and no id.
   - Rules both must follow, written into their brief: never copy a sentence or a phrase, never name a person, customer, company, repository, project, path or URL, return at most 30 lines, write nothing to disk, read no other file.
4. **Interview: six stems plus the pick rounds, four questions per call.** Section 8 of `references/report-template.md`, with AskUserQuestion, at most four questions per call. On an agent without AskUserQuestion (Codex, Cursor, OpenCode and others), ask in chat, four at a time, each with lettered options and a free-text line, and wait for the answer before the next batch.
   - **Plan the count, then say what is coming.** Work out the gates and the splits before the first call: six stems, each becoming two questions when its evidence lists more than four candidates; one pick question per four fired cards; one closing question. Calls = that count divided by four, rounded up; time = about a minute per question. Ten questions in three calls is the floor with no splits and eight or fewer fired cards; on a heavy history it is fifteen in four. One message first, with the real numbers: the session and turn counts, how many questions, how many batches, the estimated minutes, any question can be skipped, "skip the rest" stops it. Number every question "k of K".
   - **8a, six stems,** as listed in the template. Multi-select. Seed options from the person's own numbers (their top ask categories, their MCP servers, their counts) so most answers are one click; each option carries its count; free text is always available. When the evidence lists more than four candidates, split into part 1 and part 2 with the same stem and four options each. Cite the primary ask count in options that name a category; the "also matched" count belongs to gates. Do not ask about repeated feedback or conciseness; the miner measures those.
   - **8b, card picks.** Take the cards whose Gate fires, order them by evidence share, keep the top twelve (the rest are recorded as not offered), and offer them four per question as a multi-select: "Which of these would you actually use?" Each option's label is the card's Short label from `references/use-cases.md` and its description is the card name followed by its Picture line; the "In chat today" line of the top card in the batch goes into the question text. Three questions cover twelve cards; fewer when fewer gates fire. Then one last question: "Which one first, and what must it show?" with the picked cards as options (the top four by evidence share if more were picked) and the note in free text; when nothing was picked, skip it and record "no first pick" in 8b. Picked cards are recorded as picked, the other offered cards as not picked, fired cards beyond the twelve as not offered, unfired cards as not asked; "hard to imagine" typed in free text is recorded as such.
   - Record the chosen options plus any free text verbatim. Never infer an answer; an unanswered question stays empty.
5. **Fill the template,** by a subagent when one is available. Give it the paths of `session_miner_report.md` and `session_miner_output.json` from both runs (full and no-cursor), the intent and flow lines from step 3, the interview answers verbatim (or "not asked" per question when the interview was skipped), `references/report-template.md` and `references/use-cases.md`. Tell it to skip the "Per-session table" and "Sessions by project" sections of the miner report and to pull only `scope`, `aggregates` and `harness_parity` from the JSON; both carry project labels. It writes `./conversation-use-cases/conversation-use-cases-<YYYY-MM-DD>.md` and returns the path, the list of `not measured` slots, and any place where the instructions did not say what to do. Its rules: every REQUIRED slot gets a value or `not measured` with one line saying why; counts from the JSON when a report table is cut (tool usage shows the top 25; the "Tracking and hand-off tools" table is complete); no project labels, session ids or paths, and an MCP server named after a person or an internal team is written by its role (for example "personal n8n", "team n8n cloud"); section 8 verbatim; section 6 built from the derivation table in `references/use-cases.md` (a row appears when its threshold holds on the report, rows ordered by share, no judgement calls); section 7 ordered by the template rule: picked cards first with the person's first pick on top, then not picked, then not offered, then not asked, and within each group by evidence share (the first metric in the card's Evidence column divided by the denominator named in `use-cases.md`, with ask categories counted as primary plus "also matched"). Counts on different scales are never compared in prose. Read the result yourself before step 6.
6. **Gate, then hand over.** Tick the five checks at the end of the template yourself after searching the report for anything that looks like a path, a project label, a session id, a name, a customer, a URL or a copied sentence. The miner's report and JSON stay on the machine for the person (they hold project labels and are not for sharing); delete anything else you created. Give the person the report path and the sharing note. They decide whether it leaves the machine.
7. **Draft the hand-over, never send it.** If a Slack drafting tool is available (for example `slack_send_message_draft` with `slack_search_users`), look up Filipe Tavares (filipe.tavares@n8n.io), create a draft DM with the sharing note, the frustration line from section 2 and the top three asks from section 3, section 6 as its numbered list, section 7 reduced to one line per card (rank, card, Fit, evidence share; Slack does not render the ten-column table) and section 8 as given, and tell the person: the draft exists, here is the link to it, attach the report file and adjust anything before sending. Never call a send tool. If no Slack tool is available, tell the person to DM the report file to Filipe Tavares on Slack with the sharing note, and print the note for them to copy.

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

Seed list: the nineteen cards in `references/use-cases.md`, each with trigger, components, interactions, evidence metric, denominator and gate. The pick questions offer at most twelve fired cards, the top twelve by evidence share. Confirm or refute them with this person's numbers and answers; add a card only when the report shows a moment none of the nineteen covers.

## Where each report section comes from

| Template section | Source |
|---|---|
| 0 Run notes | Scope table (window, programmatic line, timezone), Sessions by harness, the discover output |
| 1 Volume and shape | Session inventory, Message length and cadence, Time distribution |
| 2 Frustrations | Frustration signals (count, share, what the assistant had just done) plus the intents subagent's frustration line |
| 3 Asks | "What the human turns ask for" (primary, also matched) plus the intents subagent's one line per category and the flow subagent's three lines |
| 4 Steering and tracking | Steering, Feedback signals, Feedback batches, Agent behaviors, Moments that point at a use-case, Tracking and hand-off tools, Agent dispatches |
| 5 Integrations | MCP servers (reads, writes, drafts, sends), Skill invocations |
| 6 Where chat fails me | The derivation table in `references/use-cases.md`, thresholds applied to the same report, plus moments with 3 or more occurrences |
| 7 Ranked use-cases | Gates and evidence shares from `references/use-cases.md`, Fit from 8b |
| 8 In my own words | The interview, verbatim |

## Mistakes seen in test runs

| Mistake | Fix |
|---|---|
| Copying a sentence, even a short one | Describe the intent in your words. Only interview answers are verbatim. |
| Reading a JSONL or database directly "just to check" | `--user-turns` is the bounded, redacted read. |
| Reading six recent sessions and calling it the person's intents | `--sample-turns` spreads the read over every session and every category; recent long sessions no longer decide the intent lines. |
| Counting continuation summaries or resubmitted prompts as human turns | The script skips them; do not add them back. |
| Guessing what a record type means | The script docstring covers `isMeta`, `origin.kind`, `promptSource`, `pr-link`, subagent folders, and each harness format. Unknown means `not measured`. |
| Inferring wishes from the data | Ask. A report that speaks for the person is not theirs. |
| Naming colleagues, customers, or other teams' repos | Roles and counts only. |
| Leaving extracted files behind | Delete before handover. |
| Treating orchestrated Cursor sessions as human interaction | Compare with `--no-cursor`; report both and say which you used. |
| Offering four options when the evidence lists eight | Split into part 1 and part 2 with the same stem; the person clicks what the miner found. |
| Opening the interview without saying how long it is | State the count, the batches and the time first; number every batch. |
| Asking a card as a label only | The Picture line is the option description; the person picks cards, they do not rate each one. |
| Asking twenty questions one card at a time | Six stems plus the pick rounds, four per call; compute the count before the first call and say it. |
| Promising "ten questions, eight minutes" and then splitting five stems | The promise comes from the computed count, not from the template. |
| Reading the session that is running the skill as one of the "most recent" sessions | It ends within the last few minutes; skip it and its parent. |
| Writing the miner output inside the skill folder | Output goes under the directory the person started in; the skill folder is a repo. |
| Reading the sample and the sessions in the main context while the person waits | Dispatch the intents and flow subagents first, then start the interview; fill the template with a subagent too. |
| Counting a one-shot eval harness as human turns | The script excludes such projects and reports it; carry the line into section 0 rather than re-adding the runs. |
| Ranking cards by raw counts | Fit first; within a Fit, evidence share with its denominator. A file-edit count never outranks a person's "fits". |
| Sending the Slack message instead of drafting it | Draft only, give the link, the person sends. |
| Asking every card regardless of the gate | Ask only cards whose gate fires. The rest are "not asked" and rank by evidence alone. |
| Calling a tool zero because it is not in the top-25 table | Use the "Tracking and hand-off tools" table or the JSON `tools` map; the top 25 is a cut. |
| Copying project labels, session ids or paths into the template | Counts and categories only; the raw report and JSON stay on the machine. |
| Summing ask categories as if they were distinct turns | One turn can hit several categories; use "also matched" for gates, primary for the intents table. |

## Sharing note

The person posts this; the agent drafts at most, and never sends.

> Ran `/conversation-use-cases` on my machine: the intents behind how I work with coding agents, how I steer and check on them, which integrations I use, and where a UI would beat chat for me. Counts and one-line intents only, no message text. Report attached.
