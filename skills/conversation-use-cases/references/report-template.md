# Conversation use-cases from my agent sessions

Generated locally with `conversation-use-cases` on <YYYY-MM-DD>. Numbers come from `session_miner_output.json`; a metric the parity table marks not measured, store absent or skipped by flag is written as `not measured`, never 0. Intents are described in my words; no message text, credentials, or names of other people are in this file. Section 8 (8a, 8b) is verbatim from me: the options I chose and the free text I typed, as I gave them.

## 0. Harnesses found (REQUIRED)

| Harness | Sessions parsed, or "detected only" | Window |
|---|---|---|
| | | |

Programmatic sessions excluded (one-shot harness runs the script detected): sessions, human turns, projects, or "none detected". Every number below excludes them unless this line says they were kept.

## 1. Volume and shape (REQUIRED)

| Metric | Value |
|---|---|
| Sessions per week, median (weeks with data) | |
| User turns per session, p50 / p90 | |
| Wall clock vs active minutes per session, p50 / p90 | |
| Longest gap between two of my turns while a session stayed open | |
| Share of my messages under 15 words / over 100 words | |
| Turns after 22:00 local | |

## 2. Intents: what I ask for (REQUIRED)

From "What the human turns ask for", top 8 categories. One line per category describing the typical intent in my own words, never a quote.

| Category | Turns | Typical intent (my words) |
|---|---|---|
| | | |

## 3. How I steer and give feedback (REQUIRED)

| Signal | Count | Share of my turns |
|---|---|---|
| Status asks | | |
| Prompts typed while the agent was running (queued) | | |
| Interrupts | | |
| Corrections | | |
| Approvals and hand-backs | | |
| Numbered or lettered answers to agent questions | | |
| Messages with pasted screenshots | | |
| Conciseness requests | | |
| Feedback batches (3+ bullets), of which with screenshots | | |
| Resumptions (my turn 30+ min after my previous one) | | |
| Frustrated messages (exasperation markers, upper bound), and the top two things the agent had just done before them | | |

One line each, in my words: how a status ask usually goes; how feedback arrives (single line or bulleted batch, with screenshots or not); how decisions get answered.

## 4. How work is tracked (REQUIRED)

| Side | Signal | Count |
|---|---|---|
| Agent's work | TaskCreate + TaskUpdate | |
| Agent's work | ScheduleWakeup + Monitor | |
| Agent's work | PushNotification | |
| Agent's work | AskUserQuestion | |
| Agent's work | Prose questions without AskUserQuestion | |
| Agent's work | Done claims, then my trust probe | |
| Agent's work | Blocked on me (asked me to do a step) | |
| Agent's work | Runs over 2 active minutes, of all runs | |
| My work | PR links | |
| My work | Artifact publishes, files pushed to me | |
| My work | Drafts vs direct sends (Slack, email) | |

## 5. Integrations (REQUIRED)

| Integration | Calls | Reads | Writes (drafts / sends) |
|---|---|---|---|
| | | | |

From the MCP servers table. Skills invoked (top 8), CLIs dominating Bash (top 8), process probes and waits, permission modes, models seen.

## 6. Where chat fails me (REQUIRED)

Ranked. Each item: the moment, the metric that shows it, the count.

1.
2.
3.

## 7. Ranked use-cases where UI beats chat (REQUIRED)

Cards come from `references/use-cases.md`. Order: picked cards first with the person's first pick on top, then not picked, then not asked. Within each group, order by evidence share: the evidence count divided by the denominator named for that card in `use-cases.md` (human turns, sessions or main-thread tool calls), written as a percentage with its denominator. Counts on different scales are never compared to each other.

| # | Use-case | Intent served | Trigger | Shows | You can | Evidence (metric, count) | Fit (8b) | Evidence share | Beats text because |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | |
| 2 | | | | | | | | | |
| 3 | | | | | | | | | |

## 8. In my own words (REQUIRED, from the interview)

Chosen options and free text recorded as given. Nothing inferred.

### 8a. How I work (six questions, always asked)

1. What do you most often have to ask for that the agent should just show you?
2. What bothers you most when working with agents?
3. What would make you trust "done", and what do you not trust the agent to report?
4. What do you still do by hand, or have taken back from the agent, and why?
5. Where would you rather click than type?
6. What must stay yours to approve or do?

### 8b. Use-case picks (cards whose gate in `references/use-cases.md` fired, offered four per question)

Fit is one of: picked, not picked, not asked, hard to imagine (typed by the person).

| # | Use-case | Fit | First pick | What it must show (free text) |
|---|---|---|---|---|
| 1 | Live run board | | | |
| 2 | Needs-you panel with one-click unblocks | | | |
| 3 | Verification board | | | |
| 4 | Decision form for batched questions, with a decision log | | | |
| 5 | Living plan and document with keep, cut and diff | | | |
| 6 | Screenshot walkthrough with comment pins | | | |
| 7 | Feedback batch triage table | | | |
| 8 | Outbound draft composer | | | |
| 9 | Errand tracker with per-step evidence | | | |
| 10 | Long-run operation console and dev-stack panel | | | |
| 11 | Analytics query workbench | | | |
| 12 | Return-to-session brief | | | |

## Privacy gate (all five must be true before sharing)

- [ ] No message text: intents are in my words, only interview answers are verbatim
- [ ] No project labels, session ids or paths copied from the raw report or JSON
- [ ] The secret-shaped string count was checked; real credentials found in my history are rotated
- [ ] No names of other people, customers, or private links
- [ ] Temporary files deleted
