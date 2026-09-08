# Conversation use-cases from my agent sessions

Generated locally with `conversation-use-cases` on <YYYY-MM-DD>. Numbers come from `session_miner_output.json`. Intents are described in my words; no message text, credentials, or names of other people are in this file. Section 8 is verbatim from me.

## 0. Harnesses found (REQUIRED)

| Harness | Sessions parsed, or "detected only" | Window |
|---|---|---|
| | | |

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

One line each, in my words: how a status ask usually goes; how feedback arrives (single line or bulleted batch, with screenshots or not); how decisions get answered.

## 4. How work is tracked (REQUIRED)

| Side | Signal | Count |
|---|---|---|
| Agent's work | TaskCreate + TaskUpdate | |
| Agent's work | ScheduleWakeup + Monitor | |
| Agent's work | PushNotification | |
| Agent's work | AskUserQuestion | |
| My work | PR links | |
| My work | Artifact publishes, files pushed to me | |
| My work | Drafts vs direct sends (Slack, email) | |

## 5. Integrations (REQUIRED)

| Integration | Calls | Read or write heavy |
|---|---|---|
| | | |

Skills invoked (top 8), CLIs dominating Bash (top 8), permission modes, models seen.

## 6. Where chat fails me (REQUIRED)

Ranked. Each item: the moment, the metric that shows it, the count.

1.
2.
3.

## 7. Ranked use-cases where UI beats chat (REQUIRED)

| # | Use-case | Intent served | Trigger | Shows | You can | Evidence (metric, count) | Beats text because |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |

## 8. In my own words (REQUIRED, from the interview)

1. What do you check most often that the agent should just show you?
2. Which feedback do you find yourself repeating?
3. Where would you rather click than type?
4. What do you wish you could see while the agent works?
5. What would make you trust "done"?

## Privacy gate (all four must be true before sharing)

- [ ] No message text: intents are in my words, only interview answers are verbatim
- [ ] The secret-shaped string count was checked; real credentials found in my history are rotated
- [ ] No names of other people, customers, or private links
- [ ] Temporary files deleted
