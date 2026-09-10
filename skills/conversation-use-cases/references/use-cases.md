# Use-case cards

Nineteen cards. Cards 1 to 12 come from the first study; 13 to 19 are the lower-frequency pages in `design/use-cases/README.md`. Each is a moment where a UI would beat chat. Every metric name below is a row or column of `session_miner_report.md` as `render_report` writes it; the dictionary gives the key under `aggregates` in `session_miner_output.json` for counts the report cuts (top-25 tables).

## Rules

- A card's Gate fires when its condition holds on this person's report. Gates are shares of a denominator or minimum counts, never bare `> 0`, so a heavy history does not fire every card. A card also fires when a moment that points at it has 3 or more occurrences in the Moments table. Cards whose gate does not fire are `not asked`.
- The pick questions offer at most twelve fired cards: the top twelve by evidence share. Fired cards outside the twelve are `not offered`. Three multi-select questions of four cards, then one first-pick question; the interview stays at ten questions.
- A metric whose parity signal reads `not measured`, `store absent on this machine` or `skipped by flag` for every harness with sessions in range is `not measured`. A gate with every metric `not measured` does not fire and the card is `not asked (not measured)`. A gate with at least one measured metric is evaluated on the measured metrics alone.
- Evidence share = the first metric in the Evidence column divided by the card's denominator, written `N of D <denominator> (P%)`. Section 7 ranks within each Fit group by this share, largest first; ties by card number.
- Fit values: `picked (first)`, `picked`, `not picked`, `hard to imagine` (typed by the person, ranks with not picked), `not offered`, `not asked`, `not asked (not measured)`.

## Short labels for the pick questions

AskUserQuestion option labels hold one to five words; the card name goes in the description with the Picture line.

| # | Short label | # | Short label | # | Short label |
|---|---|---|---|---|---|
| 1 | Run board | 8 | Draft composer | 15 | Parallel attempts |
| 2 | Needs-you list | 9 | Errand tracker | 16 | Deliverable locator |
| 3 | Verification board | 10 | Long-run console | 17 | Option picker |
| 4 | Decision form | 11 | Analytics workbench | 18 | Consequential gate |
| 5 | Living plan | 12 | Return brief | 19 | Meeting companion |
| 6 | Screenshot pins | 13 | Findings board | | |
| 7 | Feedback triage | 14 | Validation register | | |

## Metric dictionary

| Metric, as written below | Report table: row or column | JSON key under `aggregates` | Parity signal |
|---|---|---|---|
| "category" ask turns | What the human turns ask for: human turns (primary) + also matched | `asks_all[category]` | human turns |
| dispatch calls | Agent dispatches: dispatch calls (Agent, Task, spawn_agent) | `agent.dispatches` | tool calls |
| parallel dispatch messages | Agent dispatches: assistant messages with 2+ Agent calls (parallel) | `agent.parallel_dispatch_msgs` | tool calls |
| max fan-out | Agent dispatches: max fan-out in one message | `agent.max_fanout` | tool calls |
| subagent type containing word | Agent dispatches: Subagent types, rows whose name contains the word, summed | `agent.subagent_types` | tool calls |
| skill containing word | Skill invocations, rows whose name contains the word, summed | `skills` | tool calls |
| TaskCreate, TaskUpdate, ScheduleWakeup, Monitor, PushNotification, SendUserFile | Tracking and hand-off tools | `tracking_tools[name]` | tool calls |
| AskUserQuestion calls | AskUserQuestion calls line (all question tools) | `ask_user_question` | tool calls |
| Artifact publishes | Artifact tool by action: publish | `artifact_actions.publish` | tool calls |
| Write/Edit on `.md` | Write/Edit by file extension: `.md` row, summed over Write, Edit, MultiEdit | `edits_by_ext[tool][".md"]` | tool calls |
| process probes and waits | Bash commands: process probes and waits line | `bash_process_probes` | tool calls |
| MCP calls, reads, writes, drafts, sends on server X | MCP servers: columns; writes already includes drafts and sends | `mcp_servers[X]` | tool calls |
| done claims | Agent behaviors: done claims | `agent_behaviors.done_claims` | assistant text |
| done then probe | Agent behaviors: done claims followed by a human trust probe | `agent_behaviors.done_claim_then_probe` | assistant text |
| prose questions | Agent behaviors: prose questions without AskUserQuestion | `agent_behaviors.prose_questions` | assistant text |
| structured questions | Agent behaviors: structured questions | `agent_behaviors.structured_questions` | tool calls |
| blocked on user | Agent behaviors: blocked on user | `agent_behaviors.blocked_on_user` | assistant text |
| retractions | Agent behaviors: retractions | `agent_behaviors.retractions` | assistant text |
| options offered | Agent behaviors: options offered (2+ alternatives in one message) | `agent_behaviors.options_offered` | assistant text |
| long replies | Agent behaviors: long replies (over 2500 chars) | `agent_behaviors.long_replies` | assistant text |
| retries after error | Agent behaviors: retries after an error result | `agent_behaviors.retries_after_error` | tool calls |
| runs over 2 minutes | Agent behaviors: runs over 2 active minutes | `agent_behaviors.long_runs_over_2min` | timestamps |
| status asks, corrections, visual requests | Feedback signals: messages per category | `feedback_messages[category]` | human turns |
| feedback batches, batches with images | Feedback batches: feedback batches, batches with pasted images | `feedback_batches`, `feedback_batches_with_images` | human turns |
| frustrated messages | Frustration signals: frustrated messages | `frustration_msgs` | human turns |
| preceding signal | Frustration signals: what the assistant had just done | `frustration_after` | assistant text |
| resumptions | Steering: resumptions | `resumptions` | timestamps |
| resumption asks | Steering: What I ask when I come back | `resumption_asks` | timestamps |
| longest gap | Session inventory: longest gap between two human turns in one session (min) | `longest_gap_between_human_turns_min` | timestamps |
| messages with images | Session inventory: human messages with at least one pasted image | `messages_with_images` | pasted images |
| secret-shaped strings | Session inventory: secret-shaped or long identifier-like strings in human text | `secret_like` | human turns |
| PR links | Session inventory: PR links recorded by the harness | `pr_links` | PR links |
| turns in hours 22 and 23 | By hour of day: human turns column, rows 22 and 23, summed | `user_turns_by_hour[22] + user_turns_by_hour[23]` | timestamps |

## Denominators

| Denominator | Report row | JSON key under `aggregates` |
|---|---|---|
| human turns | Session inventory: human user turns | `user_turns` |
| main-thread tool calls | Session inventory: tool calls (main thread) | `tool_calls` |
| assistant messages | Session inventory: assistant messages (main thread) | `assistant_turns` |
| assistant text messages | Agent behaviors: assistant messages with text | `agent_behaviors.assistant_text_msgs` |
| runs | Agent behaviors: runs (assistant activity between two human turns) | `agent_behaviors.runs.count` |
| done claims | Agent behaviors: done claims | `agent_behaviors.done_claims` |
| frustrated messages | Frustration signals: frustrated messages | `frustration_msgs` |
| main-thread Write and Edit calls | Tool usage: Write + Edit + MultiEdit rows (JSON `tools` when cut) | `tools.Write + tools.Edit + tools.MultiEdit` |

## Cards

The first metric in the Evidence column is the ranking metric; it is on the same scale as the card's denominator.

| # | Use-case | Trigger (behavior) | Shows (components) | You can (interactions) | Evidence metric | Gate |
|---|---|---|---|---|---|---|
| 1 | Live run board | Two or more subagents dispatched, or a plan with 3+ items | Plan items by wave with state (queued, implementing, in review, fix round n, done, blocked); agent roster with elapsed time and files owned; CI state; last update stamp | Collapse, reorder, skip, ask for detail on one item, message one agent, cancel a lane | dispatch calls; parallel dispatch messages; "status or steering" ask turns; TaskCreate | dispatch calls >= 1% of main-thread tool calls, or parallel dispatch messages >= 5, or status asks >= 3% of human turns |
| 2 | Needs-you panel with one-click unblocks | The agent hits a human-only step (approve or merge a PR, register a redirect URI, unlock the machine, provide a key) | Each blocker with why, what it unblocks, exactly one control; secrets go into a masked field, never the composer | Done, paste securely, defer, ask the agent to do it itself | blocked on user; "unblock or manual step" ask turns; PushNotification; secret-shaped strings | blocked on user >= 1% of assistant text messages, or "unblock or manual step" ask turns >= 1% of human turns, or secret-shaped strings >= 5, or PushNotification >= 1 |
| 3 | Verification board | The agent claims done | Per item: merged, CI, deployed, tagged, updated on device, data landed, each with a live probe or linked artifact | Re-run a probe, expand evidence, accept | done then probe; done claims; "trust check" ask turns | done then probe >= 1% of done claims, or "trust check" ask turns >= 1% of human turns |
| 4 | Decision form for batched questions, with a decision log | A grill round or 3+ questions with recommendations | Each question with default, options (yes, no, you decide, custom), impact note; a persisted decision log so nothing is re-litigated | Answer all in one pass, batch "you decide", lock a decision | prose questions; AskUserQuestion calls; options offered; "answer questions" ask turns | prose questions >= 10 and prose questions >= 2 x structured questions, or "answer questions" ask turns >= 2% of human turns |
| 5 | Living plan and document with keep, cut and diff | The agent writes or rewrites a plan, spec or document | Previous vs proposed side by side, each block tagged kept, added, removed; a density control; version history | Toggle blocks, set density, approve once, comment on a section | Write/Edit on `.md`; "plan or design" ask turns; corrections | Write/Edit on `.md` >= 10% of main-thread Write and Edit calls, or "plan or design" ask turns >= 3% of human turns |
| 6 | Screenshot walkthrough with comment pins | UI code changes, a fix wave lands, or "show me" | Screenshot grid per view diffed against the previous revision, per-image last-updated stamp, side by side with the approved mockup | Pin a comment on a region, mark resolved, request a re-shoot, turn a pin into a task | messages with images; "show me" ask turns; visual requests | messages with images >= 1% of human turns, or "show me" ask turns >= 2% of human turns |
| 7 | Feedback batch triage table | A bulleted feedback batch arrives | One row per bullet with the agent's interpretation, state (done, doing, skipped, needs decision), linked commit or PR | Correct an interpretation inline, approve a skip, attach a screenshot | feedback batches; batches with images; "feedback or correction" ask turns; corrections | feedback batches >= 2% of human turns, or corrections >= 5% of human turns |
| 8 | Outbound draft composer | Any Slack message, DM reply, Notion page, PR description or email | The rendered message as the recipient sees it, destination visible, recurring knobs as toggles | Edit inline, then draft or send yourself | MCP drafts + sends summed over all servers; MCP calls on servers containing slack, gmail, mail or notion; "comms or drafts" ask turns | MCP drafts + sends >= 5 on any server, or "comms or drafts" ask turns >= 2% of human turns |
| 9 | Errand tracker with per-step evidence | A multi-step personal automation runs | Steps with state and evidence (receipt number, filename, screenshot); blockers with cause and a retry | Unblock, confirm a consequential step, supply the missing input, resend | MCP calls on servers containing n8n | MCP calls >= 10 on any server containing n8n |
| 10 | Long-run operation console and dev-stack panel | Any turn over about 2 minutes, or "start the server again" | Phases, elapsed, log tail, last error, retry count; services with ports, health, uptime and URL | Retry, cancel, restart a service, keep alive, open the URL | runs over 2 minutes; process probes and waits; ScheduleWakeup + Monitor; "ops or deploy" ask turns | runs over 2 minutes >= 20% of runs, or process probes and waits >= 1% of main-thread tool calls |
| 11 | Analytics query workbench | A SQL or analytics result is produced | Query, result table, chart, filters, confidence tier | Edit a filter and rerun, pin the query to a doc, change the window | "analytics or data" ask turns; MCP calls on servers containing posthog, bigquery or neon | "analytics or data" ask turns >= 1% of human turns, or MCP calls >= 5 on any such server |
| 12 | Return-to-session brief | Reopening a session after a gap | What changed, what settled, what needs you, what failed since your last turn | Jump to the item, acknowledge, continue | resumptions; resumption asks; longest gap; turns in hours 22 and 23; ScheduleWakeup | resumptions >= 5% of human turns, or longest gap > 240 |
| 13 | Review findings board | A review subagent or review skill returns findings, or the person asks for a review | Findings grouped by area and severity, each with file, evidence and state (open, accepted, rejected, in fix wave) | Accept, reject, merge duplicates, send accepted findings as one fix wave, filter by severity | "review or verify" ask turns; subagent type containing review; skill containing review | subagent type containing review >= 5, or skill containing review >= 2, or "review or verify" ask turns >= 5% of human turns |
| 14 | Validation register | The agent states that something is verified, or withdraws an earlier claim | One row per claim: verdict, evidence link, who validated (agent, subagent, probe, you), confidence | Accept, contest, re-run the check, mark as verified by hand | retractions; done claims; done then probe | retractions >= 1% of assistant text messages, or done then probe >= 2% of done claims |
| 15 | Parallel attempts | The same task dispatched to two or more agents in one message | Attempts side by side with the differences between them and a score per criterion | Pick one, merge parts, rerun with a constraint, discard | parallel dispatch messages; max fan-out; dispatch calls | parallel dispatch messages >= 3 and max fan-out >= 3 |
| 16 | Deliverable locator | A run produced files, links, artifacts or PRs, or the person asks where something is | Every output of the thread with kind, live state (published, stale, server down, merged) and last update stamp | Open, copy the link, re-publish, share, pin | "locate deliverable" ask turns; Artifact publishes; SendUserFile; PR links | "locate deliverable" ask turns >= 3, or Artifact publishes >= 5, or SendUserFile >= 5 |
| 17 | Design option picker | The agent offers two or more UI directions, or a design or brainstorm skill runs | Each direction as a rendered mock with its tradeoff note, side by side or as a slider | Pick, mix parts of two, add a constraint and rerun, reject all | options offered; visual requests; skill containing design or brainstorm | options offered >= 1% of assistant text messages, and (visual requests >= 1% of human turns or skill containing design or brainstorm >= 1) |
| 18 | Consequential gate | An irreversible call is about to happen (send, publish, deploy, delete, payment) | The call, its target and scope, a dry-run preview, the rule that would auto-approve it next time | Approve, deny, edit then approve, save a rule | MCP writes summed over all servers; MCP sends summed over all servers; "approve or hand back" ask turns | MCP writes >= 5 on any server, or "approve or hand back" ask turns >= 3% of human turns |
| 19 | Meeting companion | A meeting transcript or notes source is read, or the person asks for decisions, actions or follow-ups from a meeting | Running record of decisions, actions and open questions with owner and time; follow-up messages drafted | Confirm or edit an item, assign, turn into a task, send the draft yourself | MCP calls on servers whose name or listed top tool contains granola, calendar, meet, zoom, fireflies, otter, gong or meeting; "docs or writing" ask turns | MCP calls >= 3 on any such server |

## Pictures, denominators and the chat contrast

The Picture line is the option description in the pick question; the "In chat today" line goes into the question text when it fits. The denominator turns the ranking metric into the evidence share.

| # | Picture (what is on screen) | In chat today | Denominator |
|---|---|---|---|
| 1 | A board beside the conversation: one card per plan item moving through queued, running, review and done, agents as chips with elapsed time | You ask "what's the status" and read a paragraph | main-thread tool calls |
| 2 | A short list beside the conversation of steps only you can do, each with one button, secrets typed into a masked field | "Please add the key and tell me when done", buried in a long reply | assistant text messages |
| 3 | A grid of claimed items against merged, CI, deployed and data landed, a green or red probe result in each cell | "Done. All tests pass." and you check by hand | human turns |
| 4 | All open questions on one form, each with a default and an impact note, plus a log of past decisions with who decided and why | Questions inside paragraphs, answered as "Q1: yes, Q2: no" | assistant text messages |
| 5 | The plan with every changed block marked kept, added or removed, a density slider from outline to prose, comments pinned to passages | A rewritten plan pasted whole, diffed in your head | main-thread tool calls |
| 6 | A grid of screenshots per view with changes highlighted, and pins you and the agent place that become tasks | Pasted images referenced as Image 1, Image 2 inside a bullet list | human turns |
| 7 | Your bulleted feedback as rows: the agent's reading of each bullet and its state (done, doing, skipped, needs you) | A summary that may silently drop items | human turns |
| 8 | The message rendered as the recipient will see it, destination shown, tone and length as toggles, and you press send | Text you copy, paste and fix | main-thread tool calls |
| 9 | A stepper for a multi-step automation with proof per step (receipt number, file) and the failing step explained with a retry | "Did we send the email?" 45 minutes later | main-thread tool calls |
| 10 | For any run over two minutes: phases, elapsed time, last error, log tail, retry and cancel; services with health and URL | Silence, then "no response" messages | runs |
| 11 | Query, result table and chart together, filters you can change and rerun, a confidence tier | SQL in a code block and a markdown table | human turns |
| 12 | When you come back: what changed, what settled, what needs you, what failed, each linking to the item | Scrolling back through everything since you left | human turns |
| 13 | Findings from the review agents in one grid, grouped by area and coloured by severity, accept and reject per row, one button to send the accepted ones as a fix wave | A long review report you read top to bottom and re-type as a task list | human turns |
| 14 | A register of every claim made this thread: verdict, the evidence behind it, who checked it and how sure, contest and re-run per row | "Verified, works as expected" in a paragraph you take on faith | assistant text messages |
| 15 | Two or more attempts at the same task side by side, differences highlighted, a score per criterion, pick or merge per attempt | Several agent reports pasted one after another, compared in your head | assistant messages |
| 16 | One list of everything this thread produced: files, links, artifacts, PRs, each with a live state and an open button | "Where is the link?" and scrolling back to find it | human turns |
| 17 | Each design direction as a rendered mock with its tradeoff, side by side, with pick, mix and constrain | "Option A, Option B, Option C" described in prose | assistant text messages |
| 18 | Before any send, publish, deploy or delete: what it will do, to what, a dry run, approve or deny, and a rule for next time | "Shall I send it?" in a reply you may miss | main-thread tool calls |
| 19 | Beside a live meeting: decisions, actions and open questions filling in as they happen, follow-ups drafted for you to send | Notes pasted after the meeting and a summary you ask for by hand | main-thread tool calls |

## Moments that point at a card

The report section "Moments that point at a use-case" (JSON `aggregates.moments.<key>` with `occurrences`, `sessions`, `cards`; per session `sessions[].moments`) counts in-session sequences. A moment with 3 or more occurrences fires the cards it names and is also a section 6 row, named for the moment, with `occurrences of sessions` as the count cell.

| Moment (report row) | JSON key | What it is | Cards |
|---|---|---|---|
| blind wait | `blind_wait` | A run over 2 active minutes followed by a human status ask | 1, 10 |
| done not done | `done_not_done` | A done claim followed by a trust probe or a correction within two human turns | 3 |
| prose question then numbered answer | `prose_question_then_numbered_answer` | The agent asked in prose, the person answered with numbered or lettered lines | 4 |
| screenshot loop | `screenshot_loop` | Image, agent done claim, another image in the same session | 6 |
| feedback batch then correction | `batch_then_correction` | A bulleted batch followed within three turns by a correction repeating a marker | 7 |
| resumption then status ask | `resumption_then_status_ask` | A return after 30+ minutes whose first turn is a status ask | 12 |
| blocked then unblock | `blocked_then_unblock` | The agent asked for a human step, the person reported doing it | 2 |
| repeated correction, 3+ per session | `repeated_correction` | Three or more corrections or conciseness asks in one session | 5 |
| frustrated after long run or tool error | `frustrated_after_run_or_error` | A frustrated turn right after a run over 2 minutes or a tool error | 10, 1 |

## Section 6: where chat fails, derived

Section 6 of the template lists every row below whose condition holds, ordered by the first share in its Count cell, largest first; ties by table order. No other rows. A row whose metric is `not measured` for this person is skipped. The two rows marked `not emitted yet` are skipped until the miner emits them.

| Breakdown | Appears when | Count cell | Cards |
|---|---|---|---|
| Blind waiting | runs over 2 minutes >= 10% of runs, and status asks + resumptions >= 1 | runs over 2 minutes of runs; status asks of human turns; resumptions of human turns | 1, 10, 12 |
| Done is not done | done then probe >= 1, or "trust check" ask turns >= 1 | done then probe of done claims; "trust check" ask turns of human turns | 3, 14 |
| Questions arrive in prose | prose questions > structured questions | prose questions of prose questions + structured questions | 4 |
| Alternatives offered as text | options offered >= 1 | options offered of assistant text messages | 17, 4 |
| Feedback dropped | feedback batches >= 1, and corrections >= 5% of human turns | feedback batches of human turns; corrections of human turns | 7 |
| Human steps lost in the transcript | blocked on user >= 1, or "unblock or manual step" ask turns >= 1 | blocked on user of assistant text messages | 2, 12 |
| Secrets through the composer | secret-shaped strings >= 1 | secret-shaped strings of human turns (upper bound: emails and long identifiers also match) | 2, 18 |
| Walls of markdown | long replies >= 10% of assistant text messages, or "conciseness" ask turns >= 1 | long replies of assistant text messages | 5, 1 |
| Silent retry loops | retries after error >= 1% of main-thread tool calls | retries after error of main-thread tool calls | 10 |
| Pointing needs screenshots | messages with images >= 1, and ("show me" ask turns >= 1 or visual requests >= 1) | messages with images of human turns | 6, 17 |
| Deliverable lost | "locate deliverable" ask turns >= 1 | "locate deliverable" ask turns of human turns | 16 |
| Frustration | frustrated messages >= 1 | frustrated messages of human turns; top two preceding signals of frustrated messages | from the map below |
| Drift from the plan | not emitted yet: proposed `plan_rewrites`, Write on a `.md` path already written in the same session | | 5, 3 |
| Re-asking a settled decision | not emitted yet: proposed `repeated_prose_questions`, a prose question repeating an earlier one in the same session | | 4 |

Frustration row: the Cards cell lists the cards of the top two preceding signals.

| Preceding signal (report label) | Card |
|---|---|
| done_claim | 3 |
| long_run | 10 |
| tool_error | 10 |
| prose_question | 4 |
| options_offered | 17 |
| long_reply | 5 |
| blocked_on_user | 2 |
| retraction | 14 |
| nothing flagged | none |
