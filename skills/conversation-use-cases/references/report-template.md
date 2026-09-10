# Conversation use-cases from my agent sessions

Generated locally with `conversation-use-cases` on <YYYY-MM-DD>. Counts and one-line intents only; no message text, credentials, or names of other people. Section 8 is verbatim from me: my answers to three open questions, as I typed them.

## Format

- Headings 0 to 8, the Privacy gate and the Report checklist are fixed, in this order. No section is added, renamed, reordered or turned into prose. Tables keep their columns and their fixed rows; a cell holds a number or one line.
- A count is written `N of D <denominator> (P%)`, for example `58 of 1,490 human turns (3.9%)`. A pair is written `p50 / p90`. A total that is itself a denominator (sessions, human turns, tool calls, assistant messages, runs) is written plain.
- A metric the parity table marks not measured, store absent or skipped by flag for every harness in range is written `not measured (<reason>)`, never 0. A metric the miner does not emit is `not measured (not emitted yet)`.
- Numbers come from `session_miner_report.md` and `session_miner_output.json` of the pass named in section 0. Metric names and denominators are those of `references/use-cases.md`. Intents are one line in my words. No project labels, session ids or paths.

## 0. Run notes (REQUIRED)

| Harness | Sessions parsed, or "detected only" | Window (first session start to last session end) |
|---|---|---|
| | | |

| Note | Value |
|---|---|
| Pass the numbers come from | all harnesses, or without Cursor (`--no-cursor`) |
| Since days | |
| Programmatic sessions excluded | N sessions, N human turns, N projects; or `none detected` |
| Other exclusions (`--exclude`) | count, or `none` |
| Timezone for hours | |
| Sessions that started before the window | yes / no |

## 1. Volume and shape (REQUIRED)

| Metric | Value |
|---|---|
| Sessions | |
| Human turns | |
| Main-thread tool calls / subagent tool calls | |
| Assistant messages / assistant text messages | |
| Runs (assistant activity between two of my turns) | |
| Sessions per week, median over weeks with data (from the Sessions per week table) | |
| Wall clock vs active minutes per session, p50 / p90 | |
| Longest gap between two of my turns in one session (min) | |
| Messages under 15 words / over 100 words | N of D human turns (P%) / N of D human turns (P%) |
| Turns in hours 22 and 23 | N of D human turns (P%) |
| Turns the miner could not classify (`other`) | N of D human turns (P%) |

## 2. Frustrations (REQUIRED)

| Item | Value |
|---|---|
| Frustrated messages (exasperation marker, upper bound) | N of D human turns (P%) |
| What the agent had just done, first | signal, N of D frustrated messages (P%) |
| What the agent had just done, second | signal, N of D frustrated messages (P%) |
| What the frustrated message asked for, top category | category, N of D frustrated messages (P%) |
| Usually about (my words, one line, from the sampled turns) | |

## 3. Asks (REQUIRED)

Top 8 categories by primary count from "What the human turns ask for", `other` excluded. One turn can hit several categories; primary is the first match.

| Category | Primary | Also matched | Typical intent (my words, one line) |
|---|---|---|---|
| | N of D human turns (P%) | N | |

| Moment | How it usually goes (my words, one line) |
|---|---|
| A status ask | |
| Feedback arriving (single line or batch, with screenshots or not) | |
| Answering the agent's questions | |

## 4. Steering and tracking (REQUIRED)

| Side | Signal | Value |
|---|---|---|
| Me | Status asks | N of D human turns (P%) |
| Me | Corrections | N of D human turns (P%) |
| Me | Messages with pasted images | N of D human turns (P%) |
| Me | Feedback batches (3+ bullets) / with images | N of D human turns (P%) / N |
| Me | Resumptions (30+ min after my previous turn) | N of D human turns (P%) |
| Me | Top ask when I come back | category, N of D resumptions (P%) |
| Me | Secret-shaped strings in my messages | N of D human turns (P%) |
| Agent | Dispatch calls / parallel dispatch messages / max fan-out | N of D main-thread tool calls (P%) / N / N |
| Agent | TaskCreate + TaskUpdate | N of D main-thread tool calls (P%) |
| Agent | ScheduleWakeup + Monitor | N of D main-thread tool calls (P%) |
| Agent | PushNotification | N of D main-thread tool calls (P%) |
| Agent | AskUserQuestion calls | N of D main-thread tool calls (P%) |
| Agent | Prose questions / structured questions | N of D assistant text messages (P%) / N |
| Agent | Done claims / done then probe | N of D assistant text messages (P%) / N of D done claims (P%) |
| Agent | Blocked on me | N of D assistant text messages (P%) |
| Agent | Retractions | N of D assistant text messages (P%) |
| Agent | Options offered | N of D assistant text messages (P%) |
| Agent | Long replies (over 2500 chars) | N of D assistant text messages (P%) |
| Agent | Retries after an error result | N of D main-thread tool calls (P%) |
| Agent | Runs over 2 active minutes | N of D runs (P%) |
| Agent | Process probes and waits | N of D main-thread tool calls (P%) |
| Agent | Write/Edit on `.md` | N of D main-thread tool calls (P%) |
| Agent | Artifact publishes / SendUserFile / PR links | N of D main-thread tool calls (P%) / N / N |

## 5. Integrations (REQUIRED)

Every row of the MCP servers table, in the report's order. Writes include drafts and sends. A server name that carries another person's or a customer's name is replaced by its kind.

| MCP server | Calls | Reads | Writes | Drafts | Sends |
|---|---|---|---|---|---|
| | | | | | |

| Skill (top 8) | Calls |
|---|---|
| | |

## 6. Where chat fails me (REQUIRED)

Rows come from the derivation table in `references/use-cases.md`: every breakdown whose condition holds, plus every moment with 3 or more occurrences from the report's Moments table, ordered by share, largest first. No other rows.

| Breakdown | Metric | Count | Cards |
|---|---|---|---|
| | | N of D <denominator> (P%) | |

## 7. Use-cases the data points at (REQUIRED, derived, not my rating)

Nineteen rows, one per card in `references/use-cases.md`, ordered by evidence share, largest first; ties by card number. Gate says whether the card's condition holds on my report. Nobody asked me to rate these cards; my words are in section 8.

| Rank | # | Use-case | Gate | Evidence metric | Evidence share |
|---|---|---|---|---|---|
| 1 | | | fired / not fired / not measured | | N of D <denominator> (P%) |

## 8. In my own words (REQUIRED, verbatim from the interview)

Three open questions, answered in free text. Nothing inferred; a skipped question stays empty.

| # | Question | My answer |
|---|---|---|
| 1 | Think of the last time working with an agent annoyed you. What happened? | |
| 2 | After the agent says it is done, what do you check or redo by hand, and why? | |
| 3 | While the agent works, what do you keep having to find out for yourself? | |

## Privacy gate (all five must be true before sharing)

- [ ] No message text: intents are in my words, only interview answers are verbatim
- [ ] No project labels, session ids or paths copied from the raw report or JSON
- [ ] The secret-shaped string count was checked; real credentials found in my history are rotated
- [ ] No names of other people, customers, or private links
- [ ] Temporary files deleted

## Report checklist (the filling agent ticks every line)

- [ ] Headings 0 to 8, Privacy gate and Report checklist present in this order; nothing added, renamed or written as prose outside the tables
- [ ] Every table keeps the template's columns and fixed rows
- [ ] Every count reads `N of D <denominator> (P%)`, a plain total, or `not measured (<reason>)`; no bare count, no bare percentage
- [ ] Section 0 names the pass, the programmatic exclusion line, other exclusions and the timezone
- [ ] Section 2 has count, share, two preceding signals, top ask and the one-line paraphrase
- [ ] Section 3 has at most eight rows, each with primary, also matched and one intent line; `other` excluded
- [ ] Section 6 rows all come from the derivation table in `use-cases.md`, ordered by share
- [ ] Section 7 has nineteen rows in share order with the Gate column filled; every share names its denominator
- [ ] Section 8 has the three questions with the answers verbatim; a skipped question stays empty
- [ ] Privacy gate ticked
