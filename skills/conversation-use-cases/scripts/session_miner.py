#!/usr/bin/env python3
"""Quantitative, privacy-preserving miner for local agent transcripts.

Reads every Claude Code session under a projects directory (default
~/.claude/projects), plus Codex CLI threads under ~/.codex Cursor agent chats from its
state.vscdb, OpenCode sessions from opencode.db, and Pi, Droid, Gemini CLI, Amp,
Copilot CLI, Goose and Hermes stores when present, and emits counts only: no message text, no file paths,
no command bodies ever reach the output. Standard library only.

Layout assumed (as written by Claude Code):

    <projects>/<project-dir>/<session-id>.jsonl                 main thread
    <projects>/<project-dir>/<session-id>/subagents/agent-*.jsonl  subagents

Main-thread files define a session (start, end, human turns, assistant
turns, tool calls). Subagent files, and events flagged isSidechain in the
main file, only contribute to the "subagent" tool buckets of the parent
session: their "user" events are the parent's prompts, not the human.

Human turn = a user event that is not isMeta, whose origin.kind (when
present) is "human", whose text does not start with one of the skipped
tags (<system-reminder>, <task-notification>, <command-, <local-command,
<bash-, <system) and is not a "[Request interrupted" marker. Interrupts
are counted separately.

Heuristics with known ceilings:
  * mid_run_steering: a human turn that arrives while the last assistant
    block was a tool_use (no final text yet). Also reports promptSource
    == "queued", the harness's own marker for a prompt typed mid-run.
  * bash_head: leading word of a Bash command after dropping setup
    segments (cd, export, set, source, nvm ... up to &&, ;, || or a
    newline), env assignments and sudo/time/exec/nohup/env wrappers.
  * active_min: sum of gaps between consecutive main-thread events, each
    gap capped at 15 minutes, so idle hours do not count as work.
  * feedback regexes are case-insensitive substring/word matches; a
    message counts once per category and once per marker it matches.
  * agent_behaviors: assistant-side regex signals (done claims, done then probe, prose vs structured questions, blocked on user, retractions, options offered, long replies, retries after an error result, runs between human turns), reported under "Agent behaviors (assistant messages)".
  * asks: primary label is the first ASK_RE match, asks_all counts every
    match; categories added for unblock or manual step, locate deliverable,
    trust check, steer mid-run, show me, conciseness, nudge or retry (a
    whole short turn), context hand-off, state or capability check, decide
    or opine, address review comments, pr or git, scope or requirement;
    per-turn shape features are bullet count (feedback batch at 3+ bullets,
    with or without images) and resumption (30+ min after the previous
    human turn).
  * moments: in-session sequences that point at a use-case card (blind
    wait, done not done, prose question then numbered answer, screenshot
    loop, batch then correction, resumption then status ask, blocked then
    unblock, repeated correction, frustrated after a long run or tool
    error), each as occurrences and sessions, under aggregates.moments.

  * programmatic: a project where 80%+ of 10+ sessions are one-shot runs
    (at most one human turn, no tool calls, or an SDK entrypoint) is a
    harness; its sessions are excluded from every count unless
    --include-programmatic is given, and the exclusion is reported.
  * frustration: human turns with an exasperation marker in their prose
    (fenced code, JSON and log lines are stripped first, pasted agent
    transcripts skipped), counted together with what the assistant had
    just done (done claim, long reply, prose question, retraction,
    options, a run over 2 minutes, a tool error).
  * --tz defaults to this machine's zone.
  * --sample-turns N: per ask category, up to N redacted human turns drawn
    across all readable sessions (one per session per pass, single-turn
    sessions skipped), plus N with frustration markers. Stdout only.

Usage:
    python3 session_miner.py --out DIR [--projects-dir P] [--since-days N]
                             [--exclude ID ...] [--tz ZONE] [--include-programmatic]
                             [--weeks 12] [--notes FILE] [--self-test]
                             [--discover] [--user-turns ID] [--sample-turns N] [--no-codex]
                             [--no-cursor] [--no-opencode] [--no-other]

Writes DIR/session_miner_output.json and DIR/session_miner_report.md.
The report's "Signals measured per harness" table (JSON key harness_parity) says
which signal each adapter really extracts: measured, partial, not measured, or
store absent on this machine.
--since-days filters files by mtime (Cursor and OpenCode by last update), so a
long-lived session can start before the window. --exclude drops any file whose path
contains the given string (session id, project dir, ...). --notes appends a
markdown file verbatim to the end of the report.
"""

import argparse
import sqlite3
import glob
import shutil
import tempfile
from urllib.parse import unquote
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SKIP_PREFIXES = (
    "<system-reminder>", "<task-notification>", "<command-name>", "<command-message>",
    "<local-command", "<bash-input>", "<bash-stdout>", "<bash-stderr>", "<system",
    "This session is being continued", "Caveat: The messages below",
)
IMAGE_RE = re.compile(r"\[Image #\d+\]")
ASK_RE = [
    ("steer mid-run", re.compile(r"\A\s*(wait|stop|hold on|pause|don'?t)\b|\b(hold on|before you|first do)\b", re.I)),
    ("nudge or retry", re.compile(r"\A\W*(?:(?:please|pls|can you|could you|just|ok|okay|now)\W+){0,2}(?:(?:\w+\W+){0,2}again|retry|redo|re-?run(?:\W+it)?|reassess|resume|continue|go on|carry on|keep going|next|run it|do it)(?:\W+(?:please|pls|now|then|it|that))*\W*\Z", re.I)),
    ("trust check", re.compile(r"\b((how )?did you (actually|really|test|run|try|check|verify)|are you sure|is it really|did we|verify that|does ?n'?t work|does not work|still broken|not working)\b", re.I)),
    ("show me", re.compile(r"\b(show me|screenshots?|preview|let me see|mockups?)\b", re.I)),
    ("locate deliverable", re.compile(r"\b(where is|where'?s|what('s| is) the (link|url)|give me the (url|link)|open it|where did you put|which file|is (it|the pr|the branch|everything) (pushed|deployed|merged|published|live|released)|are (all |the )?prs? (ready|merged|open|green)|do we have (the|a|any) (branch|pr|link|build|release) (pushed|open|ready|up))\b", re.I)),
    ("unblock or manual step", re.compile(r"\b(done on my (side|end)|I (just )?did (it|that|this)|I (created|set ?up|installed|enabled|configured)|pasted|logged in|(I |we )?(approved|merged) (it|the|them)|unlocked|added the (key|token|secret)|here('s| is) the (token|key|url|link)|registered)\b", re.I)),
    ("context hand-off", re.compile(r"\A\W*https?://\S+\W*\Z|\A# Files mentioned by the user|\b(here (are|is|'s) (the|my|a|an|some|what)|here you go|for (your )?(reference|context)|fyi|attached (is|are|file|below)|the (keys?|tokens?|creds?|credentials?|secrets?|env( vars?)?|variables?) (are|is) (set|there|in place|configured|ready)|I (use|run|am on|'m on) (nvm|pnpm|yarn|bun|node|docker|zsh|fish|brew|homebrew|macos|linux|windows|a mac))\b", re.I)),
    ("state or capability check", re.compile(r"\b(are you (connected|able to|allowed to|running|using|aware|still (running|working|there))|do you (have access|know (which|what|where))|can you (see|access|reach|still)|which (model|version|branch|account|workspace) (are you|is this|am I|are we)|what can you do|is (it|the server|the app|everything|anything) (still )?(running|up|alive|connected)|what('s| is) running)\b|\A\W*(hi|hello|hey)\b", re.I)),
    ("status or steering", re.compile(r"\b(progress|status|what('s| is| are we) missing|state of (our|the) work|where are we|have you|what do you need|continue|go on|what('s| is| has)? (changed|left|next|remaining|been done)|what did you (do|change)|is (it|everything) (ready|green|done)|are (all |the )?(tests|checks) (ready|green|passing))\b", re.I)),
    ("approve or hand back", re.compile(r"^\s*(yes|ok|okay|go ahead|approved|lgtm|proceed|merged|deployed|done)\b", re.I)),
    ("answer questions", re.compile(r"(?m)^\s*(Q\d+|[A-D]\d*|\d+)\s*[:.)-]|\A\W*(go with|option|pick|choose|take|let'?s (do|go with))\s+[A-D]\b|\A\W*[A-D]\W*\Z", re.I)),
    ("decide or opine", re.compile(r"\b(what would you (do|recommend|suggest|pick|choose|go with)|what do you (think|recommend|suggest)|your (call|recommendation|pick|choice)|you (decide|choose|pick)|up to you|I('d| would) (go|pick|choose|prefer)|I prefer|my preference|sounds good|makes sense|parece-me bem|faz sentido|I('m| am) (fine|ok|okay|happy) with|let'?s go with|agreed|fair enough)\b", re.I)),
    ("conciseness", re.compile(r"\b(concise|shorter|too long|tl;?dr|less text)\b", re.I)),
    ("address review comments", re.compile(r"\b(address (the |all |those |these )?(comments|findings|feedback|review)|(comments|findings) (on|added to|left on|from) the pr|react to (the )?comments|resolve the (comments|threads|conversations))\b", re.I)),
    ("feedback or correction", re.compile(r"\b(no,|not what|wrong|instead|should have|I do not want|I don't want|remove|again|fix this|not great|not good)\b", re.I)),
    ("pr or git", re.compile(r"\b(open (a |the |up a )?pr|pull requests?|prs?|commit (the|this|these|it|everything|changes|and push)|push (it|the|this|to|everything)|(create|open|switch to|checkout|delete) (a |the )?(new )?(branch|worktree)|rebase|merge (it|the pr|main|master|into)|squash|cherry-?pick|force[- ]push)\b", re.I)),
    ("implement or fix", re.compile(r"\b(implement|build|add|create|fix|refactor|migrate|update the code|write the code|make it work|feature|bug|failing)\b", re.I)),
    ("review or verify", re.compile(r"\b(review|verify|test it|check (the|that|if)|validate|audit|qa\b)", re.I)),
    ("plan or design", re.compile(r"\b(plan|design|brainstorm|architecture|spec|approach|options|tradeoffs?|grill)\b", re.I)),
    ("research or explain", re.compile(r"\b(research|investigate|explain|why (is|does|did)|how (does|do|is)|compare|find out|look into|what is)\b", re.I)),
    ("docs or writing", re.compile(r"\b(doc|document|write up|write a|readme|notion page|article|summary|summari[sz]e|recap|brief|report)\b", re.I)),
    ("analytics or data", re.compile(r"\b(sql|query|bigquery|dashboard|metric|conversion|funnel|chart|posthog|analytics)\b", re.I)),
    ("ops or deploy", re.compile(r"\b(deploy|release|tag|docker|server|restart|ci\b|pipeline|prod|cloudflare|vercel)\b", re.I)),
    ("comms or drafts", re.compile(r"\b(slack|message to|reply to|email|draft|announce|dm\b|post in)\b", re.I)),
    ("tickets or tracking", re.compile(r"\b(linear|issue|ticket|todo|task list|backlog)\b", re.I)),
    ("scope or requirement", re.compile(r"\b(we (should|need to|also need to|must|want to|don'?t want to|do not want to|also want|should also|should not|shouldn'?t)|make sure|do not (care|need|worry|bother)|don'?t (care|need|worry|bother)|out of scope|not (now|yet|for now)|for now|leave (it|that|this) (for later|alone|as is)|skip (it|that|this)|only (do|change|touch|keep|for)|keep (it|them|the \w+) as (is|it is)|no need (to|for))\b", re.I)),
]
UNBLOCK_REPLY_RE = re.compile(r"\A\W*(?:(?:ok|okay|yes|alright)\W+)?(done|merged|deployed|added|pasted|set|created|installed|approved|restarted|logged in|ran it|it'?s (there|set|done|in))\b", re.I)
MOMENTS = (
    ("blind_wait", "blind wait: run over 2 active minutes, then a status ask", "01, 10"),
    ("done_not_done", "done not done: done claim, then a probe or correction within two turns", "03"),
    ("prose_question_then_numbered_answer", "question in prose, then a numbered or lettered answer", "04"),
    ("screenshot_loop", "screenshot loop: image, done claim, image again", "06"),
    ("batch_then_correction", "feedback batch, then a correction within three turns", "07"),
    ("resumption_then_status_ask", "resumption, then a status ask", "12"),
    ("blocked_then_unblock", "blocked on user, then an unblock or manual step", "02"),
    ("repeated_correction", "repeated correction or conciseness, 3 or more in one session", "05"),
    ("frustrated_after_run_or_error", "frustrated turn after a long run or a tool error", "10, 01"),
)


def classify_asks(text):
    return [label for label, rx in ASK_RE if rx.search(text)] or ["other"]


def classify_ask(text):
    return classify_asks(text)[0]


BULLET_RE = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S")
BATCH_MIN_BULLETS = 3
RESUME_GAP_S = 1800
CODEX_AMBIENT_RE = re.compile(r"<(in-app-browser-context|environment_context|permissions_instructions|skills_instructions|user_instructions)[^>]*>.*?</\1>", re.S)
CODEX_REQUEST_RE = re.compile(r"## My request for Codex:\s*(.*)", re.S)
INTERRUPT_PREFIX = "[Request interrupted"
TYPE_RE = re.compile(r'"type"\s*:\s*"(user|assistant|pr-link)"')
MCP_RE = re.compile(r"^mcp__(.+?)__(.+)$")
MCP_READ_RE = re.compile(r"(^|[_\-])(get|list|search|read|fetch|query|describe|find|check)", re.I)
MCP_WRITE_RE = re.compile(r"(^|[_\-])(create|update|delete|send|post|save|set|add|move|publish|reply|upload|write|execute|run|deploy|archive|share|mutate|remove|forward|trash|label|mark|merge|submit|start|stop|restart|reset)", re.I)
MCP_DRAFT_RE = re.compile(r"draft", re.I)
MCP_SEND_RE = re.compile(r"(^|[_\-])(send|post|reply|forward)($|[_\-])", re.I)
DISPATCH_TOOLS = ("Agent", "Task", "spawn_agent")
QUESTION_TOOLS = ("AskUserQuestion", "request_user_input", "ask_user_question", "ask_user", "question")
TRACKING_TOOLS = ("TaskCreate", "TaskUpdate", "TaskList", "TodoWrite", "todo_write", "update_plan", "update_current_step",
                  "ScheduleWakeup", "Monitor", "PushNotification", "SendUserFile", "Artifact", "SendMessage", "Skill") + QUESTION_TOOLS + DISPATCH_TOOLS
FRUSTRATION_RE = [re.compile(pat, re.I) for pat in (
    r"\bwtf\b", r"\bffs\b", r"\bI (already )?told you\b", r"\bI already (said|asked|mentioned|explained)\b",
    r"\bwhy (did|do|would|are) you\b", r"\bstop (doing|adding|changing|removing|ignoring|repeating)\b", r"\bnot again\b",
    r"\bthis is (wrong|broken|not working|useless|unacceptable)\b", r"!{2,}", r"\b(damn|shit|fuck|crap)\w*",
    r"\bfor the (second|third|2nd|3rd|nth|last) time\b", r"\bdon'?t ever\b", r"\bnever (do|add|change|touch) that again\b",
    r"\bare you (kidding|serious|listening|even)\b", r"\byou (keep|still|again) (doing|ignoring|adding|breaking|changing)\b",
    r"\bnot what I asked\b", r"\bunbelievable\b", r"\bI give up\b",
    r"\bsucks?\b", r"\bbullshit\b", r"\?!|!\?", r"\b(no|stop)!", r"\bstill (broken|fucked|not working|the same)\b",
    r"\bnot (addressing|listening to|reading|following) (my|what|the)\b",
)]
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
PASTE_LINE_RE = re.compile(r'(?m)^[ \t]*(?:[{}\]"\'<>|#/\\]|\[\s*(?:[{\["\]]|$)|\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|at \S+:\d+).*$')
TRANSCRIPT_RE = re.compile(r"\[\d+\] (?:user|assistant|tool)\b|TRANSCRIPT DELTA|^\s*(?:user|assistant|human|ai):\s", re.M | re.I)


def prose_only(text):
    if TRANSCRIPT_RE.search(text):
        return ""
    return PASTE_LINE_RE.sub("", CODE_FENCE_RE.sub("", text))


def is_frustrated(text):
    prose = prose_only(text)
    return any(rx.search(prose) for rx in FRUSTRATION_RE)
PROGRAMMATIC_SHARE = 0.8
PROGRAMMATIC_MIN_SESSIONS = 10
PROGRAMMATIC_ENTRYPOINTS = ("sdk", "codex_exec", "codex_sdk")
PROBE_HEADS = {"lsof", "curl", "ps", "pgrep", "netstat", "nc", "wget", "ping", "kill", "pkill", "sleep", "until"}
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEGMENT_RE = re.compile(r"^(?:[^\n;&|]|&(?!&)|\|(?!\|))*?(?:&&|\|\||;|\n)\s*")
SETUP_HEADS = {"cd", "export", "set", "source", ".", "nvm", "unset", "ulimit", "pushd"}
WRAPPERS = {"sudo", "command", "exec", "time", "nohup", "env"}
ACTIVE_GAP_CAP_S = 900
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

FEEDBACK = {
    "numbered_answers": [r"(?m)^\s*Q\s*\d{1,2}\s*[:.)\-]", r"(?m)^\s*\d{1,2}\s*[:.)\-]\s*\S.{0,60}$", r"(?m)^\s*[A-Da-d]\s*[:.)]\s*\S.{0,60}$"],
    "corrections": [
        r"\bno,", r"\bnot what\b", r"\bI do not want\b", r"\bI don'?t want\b", r"\bwrong\b",
        r"\bagain\b", r"\byou should\b", r"\bbe more concise\b", r"\btoo long\b", r"\bremove\b",
    ],
    "status_asks": [r"\bprogress\b", r"\bstatus\b", r"\bwhere are we\b", r"\bdid we\b", r"\bhave you\b"],
    "approvals": [r"^\s*(yes|ok|okay)\b", r"\bgo ahead\b", r"\bapproved\b", r"\blgtm\b", r"\bproceed\b"],
    "visual_requests": [
        r"\bartifact", r"\bscreenshot", r"\bmockup", r"\bdiagram", r"\bprototype",
        r"\bcollapsible\b", r"\bdashboard",
    ],
}
FEEDBACK_RE = {
    cat: [(p, re.compile(p, re.IGNORECASE)) for p in pats] for cat, pats in FEEDBACK.items()
}
AGENT_RE = {
    "done_claims": re.compile(r"\b(done|fixed|implemented|complete|completed|all tests pass|merged|deployed|shipped|works now)\b", re.I),
    "probe": re.compile(r"\b(did you actually|are you sure|did we|is it really|verify|check that|doesn'?t work|does not work|not working|still (broken|failing|not|wrong))\b", re.I),
    "prose_questions": re.compile(r"\b(should I|do you want|which|would you like|do you prefer|can you|could you|let me know)\b", re.I),
    "blocked_on_user": re.compile(r"\b(you need to|I need you to|please (run|provide|paste|approve)|manually|from your side|on your end|I can'?t do this without|requires your)\b", re.I),
    "retractions": re.compile(r"\b(you'?re right|you are right|I was wrong|my mistake|apologies|I apologize|I misread|I misunderstood)\b", re.I),
}
OPTION_LINE_RE = re.compile(r"(?mi)^\W{0,6}(option|approach)\b")
LETTER_LINE_RE = re.compile(r"(?m)^\W{0,4}[A-D]\)")
NUMBERED_LINE_RE = re.compile(r"(?m)^\W{0,4}([12])\.")
ALTERNATIVE_RE = re.compile(r"\b(options?|approach(es)?|alternatives?|recommend)\b", re.I)
LONG_REPLY_CHARS = 2500
LONG_RUN_S = 120
AGENT_KEYS = ("assistant_text_msgs", "done_claims", "done_claim_then_probe", "prose_questions", "structured_questions",
              "blocked_on_user", "retractions", "options_offered", "long_replies", "retries_after_error", "tool_results")


def parse_ts(s):
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def pct(values, p):
    if not values:
        return None
    vals = sorted(values)
    idx = max(0, math.ceil(p / 100 * len(vals)) - 1)
    return vals[idx]


def bash_head(cmd):
    if not isinstance(cmd, str):
        return "(non-string)"
    cmd = cmd.strip()
    for _ in range(8):
        head = first_word(cmd)
        m = SEGMENT_RE.match(cmd)
        if head in SETUP_HEADS and m:
            cmd = cmd[m.end():]
            continue
        return head
    return head


def first_word(cmd):
    for tok in cmd.split():
        tok = tok.lstrip("({").strip("\"'")
        if not tok or ENV_RE.match(tok) or tok in WRAPPERS or tok in ("&&", "||", ";"):
            continue
        return os.path.basename(tok)[:30]
    return "(empty)"


def user_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(parts) if parts else None
    return None


class Session:
    def __init__(self, session_id, project):
        self.session_id = session_id
        self.project = project
        self.start = None
        self.end = None
        self.prev_ts = None
        self.active_s = 0.0
        self.entrypoint = None
        self.user_turns = 0
        self.assistant_msgs = set()
        self.tool_calls = Counter()
        self.sub_tool_calls = Counter()
        self.subagent_files = 0
        self.mcp = Counter()
        self.skills = Counter()
        self.agent_types = Counter()
        self.agent_per_msg = Counter()
        self.artifact_actions = Counter()
        self.edits_by_ext = defaultdict(Counter)
        self.bash_heads = Counter()
        self.feedback = Counter()
        self.markers = Counter()
        self.msg_lens = []
        self.turn_ts = []
        self.turn_hours = Counter()
        self.interrupts = 0
        self.queued = 0
        self.steer = 0
        self.skipped_user_events = 0
        self.bad_lines = 0
        self.last_assistant_block = None
        self.harness = "claude-code"
        self.parent = None
        self.originator = None
        self.models = Counter()
        self.permission_modes = Counter()
        self.secret_like = 0
        self.pasted_images = 0
        self.words_short = 0
        self.words_long = 0
        self.pr_links = 0
        self.longest_gap_s = 0.0
        self.asks = Counter()
        self.msgs_with_images = 0
        self.frustration = 0
        self.frustration_after = Counter()
        self.frustration_asks = Counter()
        self.last_asst_flags = set()
        self.last_run_long = False
        self.last_tool_error = False
        self.asks_all = Counter()
        self.batch_bullets = []
        self.batches_with_images = 0
        self.resumptions = 0
        self.resume_asks = Counter()
        self.agent_sig = Counter()
        self.asst_lens = []
        self.cur_msg_id = None
        self.cur_text = []
        self.cur_tools = []
        self.pending_done = False
        self.tool_ids = {}
        self.error_tools = set()
        self.run_open = False
        self.run_tools = 0
        self.run_active_s = 0.0
        self.run_prev_ts = None
        self.runs_tools = []
        self.runs_s = []
        self.moments = Counter()
        self.done_countdown = 0
        self.batch_countdown = 0
        self.blocked_countdown = 0
        self.image_seen = False
        self.done_since_image = False
        self.density_turns = 0

    def run_touch(self, ts):
        self.run_open = True
        if ts is None:
            return
        if self.run_prev_ts is not None and ts > self.run_prev_ts:
            self.run_active_s += min((ts - self.run_prev_ts).total_seconds(), ACTIVE_GAP_CAP_S)
        self.run_prev_ts = ts

    def close_run(self, ts):
        if self.run_open:
            self.last_run_long = self.run_active_s > LONG_RUN_S
            self.runs_tools.append(self.run_tools)
            self.runs_s.append(self.run_active_s)
        self.run_open = False
        self.run_tools = 0
        self.run_active_s = 0.0
        self.run_prev_ts = ts

    def run_stats(self):
        tools = self.runs_tools + ([self.run_tools] if self.run_open else [])
        secs = self.runs_s + ([self.run_active_s] if self.run_open else [])
        return tools, secs

    def tool_issued(self, name):
        self.run_open = True
        self.run_tools += 1
        if name in self.error_tools:
            self.agent_sig["retries_after_error"] += 1
        self.error_tools.clear()

    def tool_result(self, name, is_error):
        self.agent_sig["tool_results"] += 1
        if is_error:
            self.last_tool_error = True
        if is_error and name:
            self.error_tools.add(name)

    def assistant_text(self, text, tools):
        structured = any(t in QUESTION_TOOLS for t in tools)
        if structured:
            self.agent_sig["structured_questions"] += 1
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            return
        flags = set()
        self.agent_sig["assistant_text_msgs"] += 1
        self.asst_lens.append(len(text))
        if len(text) > LONG_REPLY_CHARS:
            self.agent_sig["long_replies"] += 1
            flags.add("long_reply")
        if AGENT_RE["done_claims"].search(text[:200]):
            self.agent_sig["done_claims"] += 1
            self.pending_done = True
            self.done_countdown = 2
            self.done_since_image = self.image_seen
            flags.add("done_claim")
        if "?" in text and not structured and AGENT_RE["prose_questions"].search(text):
            self.agent_sig["prose_questions"] += 1
            flags.add("prose_question")
        for k in ("blocked_on_user", "retractions"):
            if AGENT_RE[k].search(text):
                self.agent_sig[k] += 1
                flags.add(k[:-1] if k == "retractions" else k)
        if "blocked_on_user" in flags:
            self.blocked_countdown = 2
        if len(OPTION_LINE_RE.findall(text)) >= 2 or len(LETTER_LINE_RE.findall(text)) >= 2 or (
                {"1", "2"} <= set(NUMBERED_LINE_RE.findall(text)) and ALTERNATIVE_RE.search(text)):
            self.agent_sig["options_offered"] += 1
            flags.add("options_offered")
        self.last_asst_flags = flags

    def flush_msg(self):
        if self.cur_msg_id is not None:
            self.assistant_text("\n".join(self.cur_text), self.cur_tools)
        self.cur_msg_id, self.cur_text, self.cur_tools = None, [], []

    def touch(self, ts):
        if ts is None:
            return
        if self.start is None or ts < self.start:
            self.start = ts
        if self.end is None or ts > self.end:
            self.end = ts
        if self.prev_ts is not None and ts > self.prev_ts:
            self.active_s += min((ts - self.prev_ts).total_seconds(), ACTIVE_GAP_CAP_S)
        self.prev_ts = ts

    def on_tool_use(self, block, msg_id, sidechain):
        name = block.get("name") or "(unnamed)"
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        if sidechain:
            self.sub_tool_calls[name] += 1
            return
        self.tool_calls[name] += 1
        self.tool_issued(name)
        if block.get("id"):
            self.tool_ids[block["id"]] = name
        m = MCP_RE.match(name)
        if m:
            self.mcp[(m.group(1), m.group(2))] += 1
        elif name == "Skill":
            self.skills[str(inp.get("skill") or "(unknown)")[:60]] += 1
        elif name in DISPATCH_TOOLS:
            self.agent_types[str(inp.get("subagent_type") or ("(default)" if name == "Agent" else name))[:40]] += 1
            self.agent_per_msg[msg_id] += 1
        elif name == "Artifact":
            self.artifact_actions[str(inp.get("action") or "publish")[:30]] += 1
        elif name in EDIT_TOOLS:
            fp = inp.get("file_path") or inp.get("notebook_path") or ""
            ext = os.path.splitext(str(fp))[1].lower() or "(none)"
            self.edits_by_ext[name][ext[:12]] += 1
        elif name == "Bash":
            self.bash_heads[bash_head(inp.get("command"))] += 1

    def on_assistant(self, ev, sidechain):
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        msg_id = msg.get("id") or ev.get("uuid") or "?"
        content = msg.get("content")
        if not sidechain:
            if msg_id != self.cur_msg_id:
                self.flush_msg()
                self.cur_msg_id = msg_id
            self.assistant_msgs.add(msg_id)
            ts = parse_ts(ev.get("timestamp"))
            self.touch(ts)
            self.run_touch(ts)
            if isinstance(msg.get("model"), str) and not msg["model"].startswith("<"):
                self.models[msg["model"][:40]] += 1
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                self.on_tool_use(block, msg_id, sidechain)
            if not sidechain:
                self.last_assistant_block = block.get("type")
                if block.get("type") == "text":
                    self.cur_text.append(str(block.get("text") or ""))
                elif block.get("type") == "tool_use":
                    self.cur_tools.append(block.get("name") or "")

    def on_user(self, ev, sidechain, tz):
        if sidechain:
            return
        ts = parse_ts(ev.get("timestamp"))
        self.touch(ts)
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        content = msg.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    self.tool_result(self.tool_ids.pop(b.get("tool_use_id"), None), bool(b.get("is_error")))
        text = user_text(content)
        if text is None:
            self.run_touch(ts)
            return
        origin = ev.get("origin") if isinstance(ev.get("origin"), dict) else {}
        stripped = text.lstrip()
        if ev.get("isMeta") or (origin and origin.get("kind") != "human") or stripped.startswith(SKIP_PREFIXES):
            self.skipped_user_events += 1
            return
        if stripped.startswith(INTERRUPT_PREFIX):
            self.interrupts += 1
            return
        images = 0
        if isinstance(msg.get("content"), list):
            images = sum(1 for b in msg["content"] if isinstance(b, dict) and b.get("type") == "image")
        self.human_turn(text, ts, tz, ev.get("promptSource") == "queued", images)

    def human_turn(self, text, ts, tz, queued=False, images=0):
        """Account one human turn. Shared by every harness adapter."""
        self.flush_msg()
        self.close_run(ts)
        self.error_tools.clear()
        flags, run_long, tool_error = self.last_asst_flags, self.last_run_long, self.last_tool_error
        self.last_asst_flags, self.last_run_long, self.last_tool_error = set(), False, False
        probe = bool(AGENT_RE["probe"].search(text))
        if self.pending_done and probe:
            self.agent_sig["done_claim_then_probe"] += 1
        self.pending_done = False
        self.user_turns += 1
        self.msg_lens.append(len(text))
        words = len(text.split())
        if words < 15:
            self.words_short += 1
        if words > 100:
            self.words_long += 1
        images += len(IMAGE_RE.findall(text))
        self.pasted_images += images
        if images:
            self.msgs_with_images += 1
        self.secret_like += len(SECRET_RE.findall(text))
        labels = classify_asks(text)
        self.asks[labels[0]] += 1
        self.asks_all.update(labels)
        bullets = len(BULLET_RE.findall(text))
        frustrated = is_frustrated(text)
        if frustrated:
            self.frustration += 1
            self.frustration_asks[labels[0]] += 1
            for fl in flags:
                self.frustration_after[fl] += 1
            if run_long:
                self.frustration_after["long_run"] += 1
            if tool_error:
                self.frustration_after["tool_error"] += 1
            if not flags and not run_long and not tool_error:
                self.frustration_after["nothing flagged"] += 1
        if bullets >= BATCH_MIN_BULLETS:
            self.batch_bullets.append(bullets)
            self.batches_with_images += 1 if images else 0
        resumed = False
        if ts is not None:
            if self.turn_ts and ts > self.turn_ts[-1]:
                gap = (ts - self.turn_ts[-1]).total_seconds()
                self.longest_gap_s = max(self.longest_gap_s, gap)
                if gap >= RESUME_GAP_S:
                    self.resumptions += 1
                    self.resume_asks[labels[0]] += 1
                    resumed = True
            self.turn_ts.append(ts)
            self.turn_hours[ts.astimezone(tz).hour] += 1
        if queued:
            self.queued += 1
        if self.last_assistant_block == "tool_use":
            self.steer += 1
        self.last_assistant_block = None
        hits = set()
        for cat, pats in FEEDBACK_RE.items():
            hit = False
            total = 0
            for pat, rx in pats:
                n = len(rx.findall(text))
                if n:
                    hit = True
                    total += n
                    self.markers[(cat, pat)] += n
            if cat == "numbered_answers" and not FEEDBACK_RE[cat][0][1].search(text) and (total < 2 or total < bullets):
                hit = False
            if hit:
                self.feedback[cat] += 1
                hits.add(cat)
        unblocked = "unblock or manual step" in labels or bool(UNBLOCK_REPLY_RE.match(text))
        self.detect_moments(labels, flags, run_long, tool_error, probe, images, bullets, resumed, hits, frustrated, unblocked)

    def detect_moments(self, labels, flags, run_long, tool_error, probe, images, bullets, resumed, hits, frustrated, unblocked):
        m = self.moments
        correction = "corrections" in hits or "feedback or correction" in labels
        status = "status or steering" in labels or "status_asks" in hits
        if run_long and status:
            m["blind_wait"] += 1
        if self.done_countdown > 0 and (probe or correction or "trust check" in labels):
            m["done_not_done"] += 1
            self.done_countdown = 0
        self.done_countdown = max(0, self.done_countdown - 1)
        if "prose_question" in flags and ("numbered_answers" in hits or "answer questions" in labels):
            m["prose_question_then_numbered_answer"] += 1
        if images:
            if self.done_since_image:
                m["screenshot_loop"] += 1
            self.image_seen = True
            self.done_since_image = False
        if self.batch_countdown > 0 and correction:
            m["batch_then_correction"] += 1
            self.batch_countdown = 0
        self.batch_countdown = max(0, self.batch_countdown - 1)
        if bullets >= BATCH_MIN_BULLETS:
            self.batch_countdown = 3
        if resumed and status:
            m["resumption_then_status_ask"] += 1
        if self.blocked_countdown > 0 and unblocked:
            m["blocked_then_unblock"] += 1
            self.blocked_countdown = 0
        self.blocked_countdown = max(0, self.blocked_countdown - 1)
        if correction or "conciseness" in labels:
            self.density_turns += 1
        if frustrated and (run_long or tool_error):
            m["frustrated_after_run_or_error"] += 1

    def assistant_turn(self, ts, msg_id, had_tool):
        self.assistant_msgs.add(msg_id)
        self.touch(ts)
        self.run_touch(ts)
        self.last_assistant_block = "tool_use" if had_tool else "text"

    def tool(self, name, ts):
        name = str(name or "(unnamed)")[:60]
        self.tool_calls[name] += 1
        self.touch(ts)
        self.run_touch(ts)
        self.tool_issued(name)
        self.last_assistant_block = "tool_use"
        m = MCP_RE.match(name)
        if m:
            self.mcp[(m.group(1), m.group(2))] += 1
        return name

    def gaps(self):
        ts = sorted(self.turn_ts)
        return [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]

    def row(self):
        self.flush_msg()
        dur = (self.end - self.start).total_seconds() / 60 if self.start and self.end else None
        gaps = self.gaps()
        run_s = self.run_stats()[1]
        if self.density_turns >= 3:
            self.moments["repeated_correction"] = self.density_turns
        return {
            "session_id": self.session_id,
            "harness": self.harness,
            "originator": self.originator,
            "project": self.project,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "duration_min": round(dur, 1) if dur is not None else None,
            "active_min": round(self.active_s / 60, 1),
            "entrypoint": self.entrypoint,
            "user_turns": self.user_turns,
            "assistant_turns": len(self.assistant_msgs),
            "tool_calls": sum(self.tool_calls.values()),
            "subagent_files": self.subagent_files,
            "subagent_tool_calls": sum(self.sub_tool_calls.values()),
            "agent_dispatches": sum(self.tool_calls.get(t, 0) for t in DISPATCH_TOOLS),
            "parallel_dispatch_msgs": sum(1 for v in self.agent_per_msg.values() if v >= 2),
            "max_fanout": max(self.agent_per_msg.values(), default=0),
            "skill_calls": self.tool_calls.get("Skill", 0),
            "artifact_calls": self.tool_calls.get("Artifact", 0),
            "ask_user_question": sum(self.tool_calls.get(t, 0) for t in QUESTION_TOOLS),
            "mcp_calls": sum(self.mcp.values()),
            "interrupts": self.interrupts,
            "queued_prompts": self.queued,
            "mid_run_steering": self.steer,
            "corrections": self.feedback.get("corrections", 0),
            "approvals": self.feedback.get("approvals", 0),
            "status_asks": self.feedback.get("status_asks", 0),
            "visual_requests": self.feedback.get("visual_requests", 0),
            "numbered_answers": self.feedback.get("numbered_answers", 0),
            "median_user_msg_chars": int(statistics.median(self.msg_lens)) if self.msg_lens else None,
            "median_turn_gap_min": round(statistics.median(gaps) / 60, 1) if gaps else None,
            "skipped_user_events": self.skipped_user_events,
            "bad_lines": self.bad_lines,
            "secret_like": self.secret_like,
            "pasted_images": self.pasted_images,
            "messages_with_images": self.msgs_with_images,
            "words_short": self.words_short,
            "words_long": self.words_long,
            "pr_links": self.pr_links,
            "longest_gap_min": round(self.longest_gap_s / 60, 1),
            "asks": dict(self.asks.most_common()),
            "asks_all": dict(self.asks_all.most_common()),
            "feedback_batches": len(self.batch_bullets),
            "feedback_batch_bullets_max": max(self.batch_bullets, default=0),
            "feedback_batches_with_images": self.batches_with_images,
            "resumptions": self.resumptions,
            "resumption_asks": dict(self.resume_asks.most_common()),
            "frustration_msgs": self.frustration,
            "frustration_after": dict(self.frustration_after.most_common()),
            "frustration_asks": dict(self.frustration_asks.most_common()),
            "moments": dict(self.moments.most_common()),
            "models": dict(self.models.most_common(5)),
            "permission_modes": dict(self.permission_modes.most_common(5)),
            "agent_behaviors": {
                **{k: self.agent_sig.get(k, 0) for k in AGENT_KEYS},
                "run_count": len(run_s),
                "long_runs_over_2min": sum(1 for x in run_s if x > LONG_RUN_S),
            },
        }


def scan_file(path, sess, tz, sidechain_default):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        scan_lines(fh, sess, tz, sidechain_default)


def scan_lines(lines, sess, tz, sidechain_default):
    for line in lines:
        if not TYPE_RE.search(line):
            continue
        try:
            ev = json.loads(line)
        except (ValueError, RecursionError):
            sess.bad_lines += 1
            continue
        if not isinstance(ev, dict):
            sess.bad_lines += 1
            continue
        sidechain = sidechain_default or bool(ev.get("isSidechain"))
        if not sidechain and sess.entrypoint is None and ev.get("entrypoint"):
            sess.entrypoint = str(ev["entrypoint"])[:30]
        if not sidechain and ev.get("permissionMode"):
            sess.permission_modes[str(ev["permissionMode"])[:20]] += 1
        t = ev.get("type")
        if t == "assistant":
            sess.on_assistant(ev, sidechain)
        elif t == "user":
            sess.on_user(ev, sidechain, tz)
        elif t == "pr-link" and not sidechain:
            sess.pr_links += 1


def project_label(dirname):
    home = os.path.expanduser("~").replace("/", "-")
    label = dirname[len(home):] if dirname.startswith(home) else dirname
    return label.strip("-") or "home"


def discover(projects_dir, since_days, excludes):
    cutoff = time.time() - since_days * 86400 if since_days else None
    sessions, skipped = [], []
    for proj in sorted(os.listdir(projects_dir)):
        pdir = os.path.join(projects_dir, proj)
        if not os.path.isdir(pdir):
            continue
        for name in sorted(os.listdir(pdir)):
            main = os.path.join(pdir, name)
            if not (name.endswith(".jsonl") and os.path.isfile(main)):
                continue
            if any(x in main for x in excludes):
                skipped.append((main, "excluded"))
                continue
            if cutoff and os.path.getmtime(main) < cutoff:
                skipped.append((main, "older than --since-days"))
                continue
            sid = name[:-6]
            subdir = os.path.join(pdir, sid, "subagents")
            subs = []
            if os.path.isdir(subdir):
                subs = [os.path.join(subdir, s) for s in sorted(os.listdir(subdir)) if s.endswith(".jsonl")]
            sessions.append((project_label(proj), sid, main, subs))
        for root, _dirs, files in os.walk(pdir):
            if root == pdir or "/subagents" in root:
                continue
            for f in files:
                if f.endswith(".jsonl"):
                    skipped.append((os.path.join(root, f), "not a session layout"))
    return sessions, skipped


def mcp_kind(tool):
    if MCP_DRAFT_RE.search(tool):
        return "drafts"
    if MCP_SEND_RE.search(tool):
        return "sends"
    if MCP_WRITE_RE.search(tool):
        return "writes"
    if MCP_READ_RE.search(tool):
        return "reads"
    return "other"


def mcp_summary(c):
    kinds = Counter()
    for tool, n in c.items():
        kinds[mcp_kind(tool)] += n
    return {"total": sum(c.values()), "reads": kinds["reads"], "writes": kinds["writes"] + kinds["drafts"] + kinds["sends"],
            "drafts": kinds["drafts"], "sends": kinds["sends"], "top_tools": dict(c.most_common(5))}


def programmatic_projects(rows):
    by_project = defaultdict(list)
    for r in rows:
        by_project[r.get("project")].append(r)
    flagged = set()
    for project, rs in by_project.items():
        if len(rs) < PROGRAMMATIC_MIN_SESSIONS:
            continue
        one_shot = 0
        for r in rs:
            ep = str(r.get("entrypoint") or "")
            shape = r.get("user_turns", 0) <= 1 and r.get("tool_calls", 0) == 0 and r.get("subagent_tool_calls", 0) == 0 and r.get("assistant_turns", 0) <= 2
            one_shot += 1 if shape or (r.get("user_turns", 0) <= 1 and ep.startswith(PROGRAMMATIC_ENTRYPOINTS)) else 0
        if one_shot / len(rs) >= PROGRAMMATIC_SHARE:
            flagged.add(project)
    return flagged


def local_tz_name():
    try:
        key = getattr(datetime.now().astimezone().tzinfo, "key", None)
        if key:
            return key
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except Exception:
        pass
    return "UTC"


def aggregate(sessions, tz, weeks):
    agg = {
        "sessions": len(sessions),
        "user_turns": 0, "assistant_turns": 0, "tool_calls": 0, "subagent_files": 0,
        "subagent_tool_calls": 0, "interrupts": 0, "queued_prompts": 0, "mid_run_steering": 0,
        "sessions_with_parallel_dispatch": 0, "parallel_dispatch_msgs": 0, "skipped_user_events": 0,
        "bad_lines": 0, "secret_like": 0, "pasted_images": 0, "words_short": 0, "words_long": 0, "pr_links": 0,
        "messages_with_images": 0, "frustration_msgs": 0,
    }
    per_harness, models, perms, asks = Counter(), Counter(), Counter(), Counter()
    asks_all, resume_asks, batch_bullets = Counter(), Counter(), []
    frustration_after, frustration_asks = Counter(), Counter()
    moments, moment_sessions = Counter(), Counter()
    resumptions = batches_with_images = 0
    longest_gap = 0.0
    tools, sub_tools, mcp, skills, agent_types = Counter(), Counter(), Counter(), Counter(), Counter()
    artifact, bash, feedback, markers = Counter(), Counter(), Counter(), Counter()
    edits = defaultdict(Counter)
    lens, gaps, durations, actives = [], [], [], []
    agent_sig, agent_by_harness, asst_lens, run_tools, run_s = Counter(), defaultdict(Counter), [], [], []
    hours_start, hours_turns, weekly, per_project, per_entry = Counter(), Counter(), Counter(), Counter(), Counter()
    dead_starts = 0
    turns_per_session = []
    now = datetime.now(timezone.utc).astimezone(tz)
    this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_starts = [this_monday - timedelta(weeks=k) for k in range(weeks - 1, -1, -1)]
    for s in sessions:
        r = s.row()
        for k in ("user_turns", "assistant_turns", "tool_calls", "subagent_files", "subagent_tool_calls",
                  "interrupts", "queued_prompts", "mid_run_steering", "parallel_dispatch_msgs",
                  "skipped_user_events", "bad_lines", "secret_like", "pasted_images", "words_short",
                  "words_long", "pr_links", "messages_with_images", "frustration_msgs"):
            agg[k] += r[k]
        per_harness[s.harness] += 1
        models.update(s.models)
        perms.update(s.permission_modes)
        asks.update(s.asks)
        asks_all.update(s.asks_all)
        resume_asks.update(s.resume_asks)
        frustration_after.update(s.frustration_after)
        frustration_asks.update(s.frustration_asks)
        moments.update(r["moments"])
        moment_sessions.update(r["moments"].keys())
        resumptions += s.resumptions
        batch_bullets.extend(s.batch_bullets)
        batches_with_images += s.batches_with_images
        longest_gap = max(longest_gap, s.longest_gap_s)
        agg["sessions_with_parallel_dispatch"] += 1 if r["parallel_dispatch_msgs"] else 0
        tools.update(s.tool_calls)
        sub_tools.update(s.sub_tool_calls)
        mcp.update(s.mcp)
        skills.update(s.skills)
        agent_types.update(s.agent_types)
        artifact.update(s.artifact_actions)
        bash.update(s.bash_heads)
        feedback.update(s.feedback)
        markers.update(s.markers)
        for tool, c in s.edits_by_ext.items():
            edits[tool].update(c)
        lens.extend(s.msg_lens)
        gaps.extend(s.gaps())
        agent_sig.update(r["agent_behaviors"])
        agent_by_harness[s.harness].update({k: r["agent_behaviors"][k] for k in ("assistant_text_msgs", "tool_results")})
        asst_lens.extend(s.asst_lens)
        rt, rs = s.run_stats()
        run_tools.extend(rt)
        run_s.extend(rs)
        hours_turns.update(s.turn_hours)
        per_project[s.project] += 1
        per_entry[r["entrypoint"] or "(unknown)"] += 1
        actives.append(r["active_min"])
        dead_starts += 1 if r["user_turns"] and not r["assistant_turns"] else 0
        if r["user_turns"]:
            turns_per_session.append(r["user_turns"])
        if r["duration_min"] is not None:
            durations.append(r["duration_min"])
        if s.start:
            local = s.start.astimezone(tz)
            hours_start[local.hour] += 1
            monday = (local - timedelta(days=local.weekday())).date()
            weekly[monday.isoformat()] += 1
    mcp_servers = defaultdict(Counter)
    for (server, tool), n in mcp.items():
        mcp_servers[server][tool] += n
    agg.update({
        "sessions_by_harness": dict(per_harness.most_common()),
        "asks": dict(asks.most_common()),
        "asks_all": dict(asks_all.most_common()),
        "resumptions": resumptions,
        "resumption_asks": dict(resume_asks.most_common()),
        "frustration_after": dict(frustration_after.most_common()),
        "frustration_asks": dict(frustration_asks.most_common()),
        "moments": {key: {"occurrences": moments.get(key, 0), "sessions": moment_sessions.get(key, 0), "cards": cards} for key, _label, cards in MOMENTS},
        "feedback_batches": len(batch_bullets),
        "feedback_batch_bullets": {"median": pct(batch_bullets, 50), "max": max(batch_bullets, default=0)},
        "feedback_batches_with_images": batches_with_images,
        "models": dict(models.most_common(10)),
        "permission_modes": dict(perms.most_common()),
        "longest_gap_between_human_turns_min": round(longest_gap / 60, 1),
        "user_msg_words": {
            "under_15_share": round(agg["words_short"] / agg["user_turns"], 3) if agg["user_turns"] else None,
            "over_100_share": round(agg["words_long"] / agg["user_turns"], 3) if agg["user_turns"] else None,
        },
        "sessions_by_project": dict(per_project.most_common()),
        "sessions_by_entrypoint": dict(per_entry.most_common()),
        "dead_start_sessions": dead_starts,
        "duration_min": {"median": pct(durations, 50), "p90": pct(durations, 90), "total": round(sum(durations), 1)},
        "active_min": {"median": pct(actives, 50), "p90": pct(actives, 90), "total": round(sum(actives), 1)},
        "tools": dict(tools.most_common()),
        "subagent_tools": dict(sub_tools.most_common()),
        "mcp_servers": {
            srv: mcp_summary(c)
            for srv, c in sorted(mcp_servers.items(), key=lambda kv: -sum(kv[1].values()))
        },
        "tracking_tools": {t: tools.get(t, 0) for t in TRACKING_TOOLS},
        "bash_process_probes": sum(n for h, n in bash.items() if h in PROBE_HEADS),
        "skills": dict(skills.most_common()),
        "agent": {
            "dispatches": sum(tools.get(t, 0) for t in DISPATCH_TOOLS),
            "parallel_dispatch_msgs": agg["parallel_dispatch_msgs"],
            "sessions_with_parallel_dispatch": agg["sessions_with_parallel_dispatch"],
            "max_fanout": max((s.row()["max_fanout"] for s in sessions), default=0),
            "subagent_types": dict(agent_types.most_common()),
        },
        "artifact_actions": dict(artifact.most_common()),
        "ask_user_question": sum(tools.get(t, 0) for t in QUESTION_TOOLS),
        "edits_by_ext": {t: dict(c.most_common()) for t, c in edits.items()},
        "bash_top25": dict(bash.most_common(25)),
        "feedback_messages": dict(feedback.most_common()),
        "feedback_markers": {f"{cat}: {pat}": n for (cat, pat), n in markers.most_common()},
        "user_msg_chars": {"count": len(lens), "median": pct(lens, 50), "p90": pct(lens, 90)},
        "turn_gap_seconds": {"count": len(gaps), "median": pct(gaps, 50), "p90": pct(gaps, 90)},
        "agent_behaviors": {
            **{k: agent_sig.get(k, 0) for k in AGENT_KEYS + ("long_runs_over_2min",)},
            "assistant_msg_chars": {"count": len(asst_lens), "median": pct(asst_lens, 50), "p90": pct(asst_lens, 90)},
            "runs": {
                "count": len(run_s),
                "tool_calls_median": pct(run_tools, 50), "tool_calls_p90": pct(run_tools, 90),
                "minutes_median": round(pct(run_s, 50) / 60, 1) if run_s else None,
                "minutes_p90": round(pct(run_s, 90) / 60, 1) if run_s else None,
            },
            "by_harness": {h: {"assistant_text_msgs": c.get("assistant_text_msgs", 0), "tool_results": c.get("tool_results", 0)}
                           for h, c in sorted(agent_by_harness.items())},
        },
        "weekly_sessions": {ws.date().isoformat(): weekly.get(ws.date().isoformat(), 0) for ws in week_starts},
        "user_turns_per_session": {"median": pct(turns_per_session, 50), "p90": pct(turns_per_session, 90)},
        "sessions_per_week_median": pct([weekly.get(ws.date().isoformat(), 0) for ws in week_starts if weekly.get(ws.date().isoformat(), 0)], 50),
        "sessions_by_hour": {h: hours_start.get(h, 0) for h in range(24)},
        "user_turns_by_hour": {h: hours_turns.get(h, 0) for h in range(24)},
    })
    return agg


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(out)


def counter_table(d, k1, k2="count", limit=None):
    items = list(d.items())[:limit] if limit else list(d.items())
    return md_table([k1, k2], items)


def render_report(agg, rows, scope, tz_name, parity=None):
    parity = parity or {}
    prog = scope.get("programmatic") or {}
    if prog.get("sessions"):
        prog_str = f"{prog['sessions']} sessions, {prog['user_turns']} human turns, {prog['projects']} project(s); " + (
            "kept in every count (--include-programmatic)" if prog.get("included") else "excluded from every count below; --include-programmatic keeps them")
    else:
        prog_str = "none detected"
    L = []
    L.append("# Agent session miner report\n")
    L.append(f"Generated {scope['generated_at']}. Timezone for hours: {tz_name}. Counts only, no message text.\n")
    L.append("## Scope\n")
    L.append(md_table(["metric", "value"], [
        ("projects dir", scope["projects_dir"]),
        ("Claude Code session files", scope["session_files"]),
        ("Codex thread files", scope.get("codex_files", 0)),
        ("Cursor agent chats", scope.get("cursor_sessions", 0)),
        ("OpenCode sessions", scope.get("opencode_sessions", 0)),
        ("subagent files", agg["subagent_files"]),
        ("skipped files", scope["skipped_files"]),
        ("since days", scope["since_days"] or "all"),
        ("excludes", ", ".join(scope["excludes"]) or "none"),
        ("first session start", scope["first_start"]),
        ("last session end", scope["last_end"]),
        ("malformed lines", agg["bad_lines"]),
        ("scan seconds", scope["scan_seconds"]),
        ("programmatic sessions (one-shot runs in harness projects)", prog_str),
    ]))
    L.append("\n### Signals measured per harness\n")
    L.append(md_table(["signal"] + list(parity), [[sig] + [parity[h][sig] for h in parity] for sig in PARITY_SIGNALS]))
    empty = [h for h in parity if parity[h]["human turns"] not in (STORE_ABSENT, SKIPPED_BY_FLAG) and not any(k.startswith(h) for k in agg["sessions_by_harness"])]
    L.append("\nmid-run steering is a heuristic on every harness: a human turn that lands after a tool call with no assistant text in between."
             + (f" Store present but no sessions in range, so the cells describe the adapter: {', '.join(empty)}." if empty else ""))
    L.append("\n## Session inventory\n")
    L.append(md_table(["metric", "value"], [
        ("sessions", agg["sessions"]),
        ("human user turns", agg["user_turns"]),
        ("human turns per session with at least one turn: median / p90", f"{agg['user_turns_per_session']['median']} / {agg['user_turns_per_session']['p90']}"),
        ("sessions per week, median over weeks with sessions", agg["sessions_per_week_median"]),
        ("assistant messages (main thread)", agg["assistant_turns"]),
        ("tool calls (main thread)", agg["tool_calls"]),
        ("tool calls (subagents)", agg["subagent_tool_calls"]),
        ("wall-clock duration min: median / p90 / total", f"{agg['duration_min']['median']} / {agg['duration_min']['p90']} / {agg['duration_min']['total']}"),
        (f"active min (gaps capped at {ACTIVE_GAP_CAP_S // 60} min): median / p90 / total", f"{agg['active_min']['median']} / {agg['active_min']['p90']} / {agg['active_min']['total']}"),
        ("sessions with human turns but no assistant reply (dead starts)", agg["dead_start_sessions"]),
        ("sessions by entrypoint", ", ".join(f"{k} ({v})" for k, v in agg["sessions_by_entrypoint"].items())),
        ("user events skipped as system/meta", agg["skipped_user_events"]),
        ("interrupts ([Request interrupted])", agg["interrupts"]),
        ("human messages under 15 words / over 100 words", f"{agg['words_short']} / {agg['words_long']} of {agg['user_turns']}"),
        ("longest gap between two human turns in one session (min)", agg["longest_gap_between_human_turns_min"]),
        ("pasted images (image blocks + [Image #n] markers in human text)", agg["pasted_images"]),
        ("human messages with at least one pasted image", agg["messages_with_images"]),
        ("PR links recorded by the harness", agg["pr_links"]),
        ("secret-shaped or long identifier-like strings in human text (count only; check and rotate real ones)", agg["secret_like"]),
        ("permission modes seen", ", ".join(f"{k} ({v})" for k, v in agg["permission_modes"].items()) or "not recorded"),
        ("models seen (see the parity table for which harnesses record them)", ", ".join(f"{k} ({v})" for k, v in agg["models"].items()) or "not recorded"),
    ]))
    L.append("\n### What the human turns ask for (primary = first matching category; also matched = further categories the same turn hit; counts only)\n")
    L.append(md_table(["ask", "human turns (primary)", "also matched"], [
        (k, agg["asks"].get(k, 0), agg["asks_all"].get(k, 0) - agg["asks"].get(k, 0))
        for k in sorted(agg["asks_all"], key=lambda k: (-agg["asks"].get(k, 0), -agg["asks_all"][k]))
    ]))
    L.append("\n### Sessions by harness\n")
    L.append(counter_table(agg["sessions_by_harness"], "harness", "sessions"))
    L.append("\n### Sessions by project\n")
    L.append(counter_table(agg["sessions_by_project"], "project", "sessions"))
    L.append("\n### Per-session table\n")
    cols = ["project", "start", "duration_min", "active_min", "user_turns", "assistant_turns", "tool_calls", "subagent_files",
            "subagent_tool_calls", "agent_dispatches", "parallel_dispatch_msgs", "artifact_calls",
            "ask_user_question", "mid_run_steering", "queued_prompts", "corrections", "approvals",
            "median_user_msg_chars", "median_turn_gap_min"]
    L.append(md_table(cols, [[(r[c][:16] if c == "start" and r[c] else r[c]) for c in cols] for r in rows]))
    L.append("\n## Tool usage\n")
    L.append("### Main thread, top 25\n")
    L.append(counter_table(agg["tools"], "tool", limit=25))
    L.append("\n### Tracking and hand-off tools (Claude Code tool names, 0 means not seen)\n")
    L.append(counter_table(agg["tracking_tools"], "tool"))
    L.append("\n### Subagents, top 15\n")
    L.append(counter_table(agg["subagent_tools"], "tool", limit=15))
    L.append("\n### MCP servers\n")
    L.append(md_table(["server", "calls", "reads", "writes", "drafts", "sends", "top tools"], [
        (srv, d["total"], d["reads"], d["writes"], d["drafts"], d["sends"], ", ".join(f"{t} ({n})" for t, n in d["top_tools"].items()))
        for srv, d in agg["mcp_servers"].items()
    ]))
    L.append("\nreads and writes are classified by the verb in the tool name; drafts and sends are the subset of writes whose name says draft, or send, post, reply, forward.\n")
    L.append("\n### Skill invocations\n")
    L.append(counter_table(agg["skills"], "skill"))
    a = agg["agent"]
    L.append("\n### Agent dispatches\n")
    L.append(md_table(["metric", "value"], [
        ("dispatch calls (Agent, Task, spawn_agent)", a["dispatches"]),
        ("assistant messages with 2+ Agent calls (parallel)", a["parallel_dispatch_msgs"]),
        ("sessions with at least one parallel dispatch", a["sessions_with_parallel_dispatch"]),
        ("max fan-out in one message", a["max_fanout"]),
    ]))
    L.append("\nSubagent types:\n")
    L.append(counter_table(a["subagent_types"], "subagent_type"))
    L.append("\n### Artifact tool by action\n")
    L.append(counter_table(agg["artifact_actions"], "action"))
    L.append(f"\nAskUserQuestion calls: {agg['ask_user_question']}\n")
    L.append("### Write/Edit by file extension\n")
    for tool, d in agg["edits_by_ext"].items():
        L.append(f"\n{tool}:\n")
        L.append(counter_table(d, "ext"))
    L.append("\n### Bash commands by leading word, top 25\n")
    L.append(counter_table(agg["bash_top25"], "command"))
    L.append(f"\nprocess probes and waits ({', '.join(sorted(PROBE_HEADS))}): {agg['bash_process_probes']}\n")
    ab = agg["agent_behaviors"]
    L.append("\n## Agent behaviors (assistant messages)\n")
    L.append(md_table(["signal", "count"], [
        ("assistant messages with text", ab["assistant_text_msgs"]),
        ("done claims (completion word in the first 200 chars)", ab["done_claims"]),
        ("done claims followed by a human trust probe (done is not done)", ab["done_claim_then_probe"]),
        ("prose questions without AskUserQuestion", ab["prose_questions"]),
        ("structured questions (AskUserQuestion in the message)", ab["structured_questions"]),
        ("blocked on user (asks the human to do a step)", ab["blocked_on_user"]),
        ("retractions", ab["retractions"]),
        ("options offered (2+ alternatives in one message)", ab["options_offered"]),
        (f"long replies (over {LONG_REPLY_CHARS} chars)", ab["long_replies"]),
        ("assistant text chars: median / p90", f"{ab['assistant_msg_chars']['median']} / {ab['assistant_msg_chars']['p90']}"),
        ("retries after an error result (same tool, next call)", ab["retries_after_error"]),
        ("runs (assistant activity between two human turns)", ab["runs"]["count"]),
        ("tool calls per run: median / p90", f"{ab['runs']['tool_calls_median']} / {ab['runs']['tool_calls_p90']}"),
        (f"active minutes per run (gaps capped at {ACTIVE_GAP_CAP_S // 60} min): median / p90", f"{ab['runs']['minutes_median']} / {ab['runs']['minutes_p90']}"),
        (f"runs over {LONG_RUN_S // 60} active minutes", ab["long_runs_over_2min"]),
    ]))
    L.append("\nPer harness: " + "; ".join(
        f"{h}: text signals {'measured' if c['assistant_text_msgs'] else 'not measured'}, retries {'measured' if c['tool_results'] else 'not measured'}"
        for h, c in ab["by_harness"].items()) + "\n")
    L.append("\n## Moments that point at a use-case\n")
    L.append("Sequences inside one session, counted as occurrences and as sessions where they occurred. Card numbers follow design/use-cases/README.md.\n")
    L.append(md_table(["moment", "occurrences", "sessions", "use-case card(s)"], [
        (label, agg["moments"][key]["occurrences"], agg["moments"][key]["sessions"], cards) for key, label, cards in MOMENTS
    ]))
    L.append("\n## Feedback signals (human messages)\n")
    L.append("Messages matching at least one marker per category:\n")
    L.append(counter_table(agg["feedback_messages"], "category", "messages"))
    L.append("\nPer marker (total matches):\n")
    L.append(counter_table(agg["feedback_markers"], "marker", "matches"))
    L.append(f"\nFeedback batches (human turns with {BATCH_MIN_BULLETS}+ bullet or numbered lines):\n")
    L.append(md_table(["metric", "value"], [
        ("feedback batches", agg["feedback_batches"]),
        ("bullets per batch, median / max", f"{agg['feedback_batch_bullets']['median']} / {agg['feedback_batch_bullets']['max']}"),
        ("batches with pasted images", agg["feedback_batches_with_images"]),
    ]))
    L.append("\n### Frustration signals (human messages with an exasperation marker; upper bound, counts only)\n")
    L.append(md_table(["metric", "value"], [
        ("frustrated messages", agg["frustration_msgs"]),
        ("share of human turns", f"{100 * agg['frustration_msgs'] / max(1, agg['user_turns']):.1f}%"),
    ]))
    L.append("\nWhat the assistant had just done before a frustrated message (a message can count under several):\n")
    L.append(counter_table(agg["frustration_after"], "preceding signal", "messages"))
    L.append("\nWhat the frustrated message asked for (primary category):\n")
    L.append(counter_table(agg["frustration_asks"], "ask", "messages"))
    L.append("\n### Steering\n")
    L.append(md_table(["metric", "value"], [
        ("human turns arriving while assistant was mid tool run (heuristic)", agg["mid_run_steering"]),
        ("prompts with promptSource=queued (harness marker)", agg["queued_prompts"]),
        ("interrupts", agg["interrupts"]),
        ("share of human turns that were mid-run", f"{100 * agg['mid_run_steering'] / max(1, agg['user_turns']):.1f}%"),
        (f"resumptions (human turn {RESUME_GAP_S // 60}+ min after the previous one in the same session)", agg["resumptions"]),
    ]))
    L.append("\nWhat I ask when I come back (primary category of resumption turns):\n")
    L.append(counter_table(agg["resumption_asks"], "ask", "resumption turns"))
    L.append("\n## Message length and cadence\n")
    L.append(md_table(["metric", "value"], [
        ("human messages", agg["user_msg_chars"]["count"]),
        ("chars median", agg["user_msg_chars"]["median"]),
        ("chars p90", agg["user_msg_chars"]["p90"]),
        ("gap between human turns, median (s)", agg["turn_gap_seconds"]["median"]),
        ("gap between human turns, p90 (s)", agg["turn_gap_seconds"]["p90"]),
    ]))
    L.append("\n## Time distribution\n")
    L.append(f"### Sessions per week (last {len(agg['weekly_sessions'])} weeks, week starting Monday)\n")
    L.append(counter_table(agg["weekly_sessions"], "week of", "sessions"))
    L.append(f"\n### By hour of day ({tz_name})\n")
    L.append(md_table(["hour", "session starts", "human turns"], [
        (h, agg["sessions_by_hour"][h], agg["user_turns_by_hour"][h]) for h in range(24)
    ]))
    return "\n".join(L) + "\n"


def self_test():
    tz = ZoneInfo("UTC")
    s = Session("t", "p")
    ts = "2026-01-05T10:00:{:02d}Z"
    events = [
        {"type": "user", "timestamp": ts.format(0), "message": {"content": "Q1: yes go ahead"}, "origin": {"kind": "human"}},
        {"type": "assistant", "timestamp": ts.format(1), "message": {"id": "m1", "model": "claude-x", "content": [
            {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "Explore"}},
            {"type": "tool_use", "name": "Agent", "input": {}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "cd /x && FOO=1 git status"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/b.ts"}},
            {"type": "tool_use", "name": "mcp__slack__send", "input": {}},
            {"type": "tool_use", "name": "Skill", "input": {"skill": "grilling"}},
            {"type": "tool_use", "name": "Artifact", "input": {"file_path": "x.html"}},
        ]}},
        {"type": "user", "timestamp": ts.format(2), "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "user", "timestamp": ts.format(3), "message": {"content": "no, wrong again"}, "promptSource": "queued"},
        {"type": "user", "timestamp": ts.format(4), "message": {"content": "<task-notification>x"}},
        {"type": "user", "timestamp": ts.format(5), "message": {"content": "[Request interrupted by user]"}},
        {"type": "user", "isMeta": True, "timestamp": ts.format(6), "message": {"content": "meta"}},
        {"type": "assistant", "timestamp": ts.format(7), "message": {"id": "m2", "content": [{"type": "text", "text": "done"}]}},
        {"type": "user", "timestamp": ts.format(8), "message": {"content": "screenshot please"}},
    ]
    scan_lines([json.dumps(e) for e in events] + ['{"type":"user", broken'], s, tz, False)
    r = s.row()
    assert r["user_turns"] == 3, r
    assert r["assistant_turns"] == 2
    assert r["tool_calls"] == 7 and r["agent_dispatches"] == 2 and r["parallel_dispatch_msgs"] == 1
    assert r["mid_run_steering"] == 1 and r["queued_prompts"] == 1 and r["interrupts"] == 1
    assert r["corrections"] == 1 and r["approvals"] == 1 and r["numbered_answers"] == 1 and r["visual_requests"] == 1
    assert s.bash_heads == Counter({"git": 1}) and s.edits_by_ext["Edit"] == Counter({".ts": 1})
    assert bash_head("set -o pipefail; pnpm test | tail") == "pnpm"
    assert bash_head('export PATH="$HOME/x:$PATH" && S=/tmp && codesign -dv "$S/a"') == "codesign"
    assert bash_head("source ~/.nvm/nvm.sh >/dev/null 2>&1 && nvm use 26 >/dev/null 2>&1 && node -v") == "node"
    assert bash_head('"$SDD/review-package" a | tail') == "review-package"
    assert bash_head("cd /repo\nW=.sdd && { echo hi; git log; }") == "echo"
    assert bash_head("/usr/bin/python3 -c 1") == "python3" and bash_head("") == "(empty)"
    assert r["active_min"] == 0.1
    assert s.mcp == Counter({("slack", "send"): 1}) and s.skills == Counter({"grilling": 1})
    assert s.artifact_actions == Counter({"publish": 1}) and s.bad_lines == 1
    assert r["skipped_user_events"] == 2 and r["duration_min"] == 0.1
    ab = r["agent_behaviors"]
    assert ab["done_claims"] == 1 and ab["done_claim_then_probe"] == 0 and ab["run_count"] == 2, ab
    s2 = Session("t2", "p")
    m = "2026-01-05T11:{:02d}:00Z"
    ev2 = [
        {"type": "user", "timestamp": m.format(0), "message": {"content": "please fix the test"}},
        {"type": "assistant", "timestamp": m.format(1), "message": {"id": "a1", "content": [{"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "pnpm test"}}]}},
        {"type": "user", "timestamp": m.format(1), "message": {"content": [{"type": "tool_result", "tool_use_id": "b1", "is_error": True, "content": "x"}]}},
        {"type": "assistant", "timestamp": m.format(2), "message": {"id": "a2", "content": [{"type": "tool_use", "id": "b2", "name": "Bash", "input": {"command": "pnpm test"}}]}},
        {"type": "user", "timestamp": m.format(2), "message": {"content": [{"type": "tool_result", "tool_use_id": "b2", "is_error": False, "content": "x"}]}},
        {"type": "assistant", "timestamp": m.format(3), "message": {"id": "a3", "content": [{"type": "tool_use", "id": "b3", "name": "Bash", "input": {"command": "pnpm lint"}}]}},
        {"type": "user", "timestamp": m.format(3), "message": {"content": [{"type": "tool_result", "tool_use_id": "b3", "content": "x"}]}},
        {"type": "assistant", "timestamp": m.format(4), "message": {"id": "a4", "content": [{"type": "text", "text": "Should I also update the docs? Let me know."}]}},
        {"type": "user", "timestamp": m.format(5), "message": {"content": "yes"}},
        {"type": "assistant", "timestamp": m.format(6), "message": {"id": "a5", "content": [{"type": "text", "text": "Done. All tests pass."}]}},
        {"type": "user", "timestamp": m.format(7), "message": {"content": "are you sure it works? verify"}},
        {"type": "assistant", "timestamp": m.format(8), "message": {"id": "a6", "content": [{"type": "text", "text": "You're right, my mistake. You need to run the migration manually.\n\n### Option A\nkeep it\n### Option B\nrewrite it\n\nWhich do you prefer?"}]}},
        {"type": "assistant", "timestamp": m.format(8), "message": {"id": "a6", "content": [{"type": "tool_use", "id": "q1", "name": "AskUserQuestion", "input": {}}]}},
        {"type": "assistant", "timestamp": m.format(9), "message": {"id": "a7", "content": [{"type": "text", "text": "x" * 2600}]}},
    ]
    scan_lines([json.dumps(e) for e in ev2], s2, tz, False)
    ab = s2.row()["agent_behaviors"]
    assert ab["assistant_text_msgs"] == 4 and ab["done_claims"] == 1 and ab["done_claim_then_probe"] == 1, ab
    assert ab["prose_questions"] == 1 and ab["structured_questions"] == 1, ab
    assert ab["blocked_on_user"] == 1 and ab["retractions"] == 1 and ab["options_offered"] == 1 and ab["long_replies"] == 1, ab
    assert ab["retries_after_error"] == 1 and ab["tool_results"] == 3, ab
    assert ab["run_count"] == 3 and ab["long_runs_over_2min"] == 1, ab
    assert s2.run_stats() == ([3, 0, 1], [240.0, 60.0, 120.0]), s2.run_stats()
    agg = aggregate([s, s2], tz, 2)
    a = agg["agent_behaviors"]
    assert a["done_claim_then_probe"] == 1 and a["retries_after_error"] == 1 and a["runs"]["count"] == 5, a
    assert a["runs"]["tool_calls_p90"] == 7 and a["runs"]["minutes_median"] == 1.0 and a["assistant_msg_chars"]["count"] == 5, a
    assert a["by_harness"]["claude-code"]["tool_results"] == 4, a
    scope = {"generated_at": "t", "projects_dir": "p", "session_files": 2, "skipped_files": 0, "since_days": None,
             "excludes": [], "first_start": None, "last_end": None, "scan_seconds": 0}
    rep = render_report(agg, [s.row(), s2.row()], scope, "UTC")
    assert 0 < rep.index("## Agent behaviors (assistant messages)") < rep.index("## Feedback signals (human messages)")
    assert "claude-code: text signals measured, retries measured" in rep
    assert "PushNotification" in rep and "drafts" in rep and agg["tracking_tools"]["Agent"] == 2 and agg["bash_process_probes"] == 0, agg["tracking_tools"]
    assert agg["mcp_servers"]["slack"] == {"total": 1, "reads": 0, "writes": 1, "drafts": 0, "sends": 1, "top_tools": {"send": 1}}, agg["mcp_servers"]
    assert mcp_kind("slack_send_message_draft") == "drafts" and mcp_kind("notion-fetch") == "reads" and mcp_kind("save_issue") == "writes" and mcp_kind("pack_query") == "reads"
    assert harness_parity({"codex"})["codex"]["human turns"] == "measured" and harness_parity(set())["cursor"]["human turns"] == STORE_ABSENT
    assert AGENT_RE["probe"].search("it is still not working") and not AGENT_RE["probe"].search("still need the docs")
    s3 = Session("t3", "p")
    scan_lines([json.dumps({"type": "user", "timestamp": "2026-01-05T12:00:00Z", "message": {"content": "is it ok to remove this?"}})], s3, tz, False)
    assert s3.feedback.get("approvals", 0) == 0 and s3.feedback.get("corrections") == 1, dict(s3.feedback)
    assert any_ts(None) is None and any_ts(1767261600) == any_ts(1767261600000) == any_ts("2026-01-01T10:00:00Z")
    assert classify_asks("wait, is it really working? show me a screenshot") == ["steer mid-run", "trust check", "show me"]
    assert classify_ask("done on my side, I added the key") == "unblock or manual step"
    assert classify_ask("merged it, next") == "unblock or manual step" and classify_ask("merged") == "approve or hand back"
    assert classify_ask("where is the file? what's the link") == "locate deliverable"
    assert classify_ask("did you actually run the tests?") == "trust check"
    assert classify_ask("hold on, before you continue") == "steer mid-run"
    assert classify_ask("show me a preview") == "show me"
    assert classify_ask("be more concise, this is too long") == "conciseness"
    assert classify_ask("What is the progress? Please be concise.") == "status or steering"
    assert classify_ask("please don't add comments") == "implement or fix"
    assert classify_ask("Try again") == "nudge or retry" and classify_ask("continue") == "nudge or retry" and classify_ask("Check again please") == "nudge or retry"
    assert classify_ask("continue with the plan and report progress") == "status or steering" and classify_ask("proceed") == "approve or hand back"
    assert classify_ask("A") == "answer questions" and classify_ask("Go with A. We need the whole plan first") == "answer questions"
    assert classify_ask("https://example.com/x/y") == "context hand-off" and classify_ask("the keys are set, trigger the job") == "context hand-off"
    assert classify_ask("Are you connected to GitHub?") == "state or capability check" and classify_ask("Hello, what can you do here?") == "state or capability check"
    assert classify_ask("what changed since yesterday?") == "status or steering" and classify_ask("Are all PRs ready to be merged?") == "locate deliverable"
    assert classify_ask("What would you do?") == "decide or opine" and classify_ask("sounds good, make sure it is published") == "decide or opine"
    assert classify_ask("Address the comments on the PR please") == "address review comments" and classify_ask("Let's address the findings!") == "address review comments"
    assert classify_ask("Open a PR with the fixes please") == "pr or git" and classify_ask("Commit the changes, then switch to master") == "pr or git"
    assert classify_ask("Now summarise each of the three in one line.") == "docs or writing"
    assert classify_ask("We need to make sure that we include the desktop app") == "scope or requirement"
    assert classify_ask("We should definitely remove everything that is legacy") == "feedback or correction"
    assert is_frustrated("this UX sucks, fix it") and is_frustrated("No! keep the webhook") and is_frustrated("specs are committed!?")
    assert not is_frustrated("[3] user: I told you\n[4] assistant: ok") and not is_frustrated("```\nif (!!x) {}\n```\nlooks fine")
    assert not is_frustrated('{"a": "wtf"}\nplease check') and is_frustrated("[Image #2] wtf, still wrong")
    s2 = Session("t2", "p")
    t2 = "2026-01-05T{}Z"
    scan_lines([json.dumps(e) for e in [
        {"type": "user", "timestamp": t2.format("10:00:00"), "message": {"content": [
            {"type": "text", "text": "feedback:\n- a\n- b\n* c\n1. d\n2) e\n[Image #1]"}, {"type": "image"}]}},
        {"type": "user", "timestamp": t2.format("10:20:00"), "message": {"content": "- x\n- y"}},
        {"type": "user", "timestamp": t2.format("10:51:00"), "message": {"content": "where are we?"}},
    ]], s2, tz, False)
    r2 = s2.row()
    assert r2["user_turns"] == 3 and r2["pasted_images"] == 2
    assert r2["feedback_batches"] == 1 and r2["feedback_batch_bullets_max"] == 5 and r2["feedback_batches_with_images"] == 1
    assert r2["resumptions"] == 1 and r2["resumption_asks"] == {"status or steering": 1}
    assert r2["asks_all"]["status or steering"] == 1
    agg = aggregate([s, s2], tz, 1)
    assert agg["resumptions"] == 1 and agg["feedback_batches"] == 1 and agg["feedback_batch_bullets"] == {"median": 5, "max": 5}
    assert agg["asks_all"]["show me"] == 1 and agg["asks"]["show me"] == 1
    rep = render_report(agg, [r, r2], {"generated_at": "", "projects_dir": "", "session_files": 0, "skipped_files": 0,
                                       "since_days": None, "excludes": [], "first_start": None, "last_end": None, "scan_seconds": 0}, "UTC")
    assert "What I ask when I come back" in rep and "also matched" in rep and "Feedback batches" in rep
    s3 = Session("t3", "p")
    t3 = "2026-01-06T{}Z"
    scan_lines([json.dumps(e) for e in [
        {"type": "user", "timestamp": t3.format("09:00:00"), "message": {"content": "please fix it"}},
        {"type": "assistant", "timestamp": t3.format("09:00:30"), "message": {"id": "c1", "content": [{"type": "tool_use", "id": "d1", "name": "spawn_agent", "input": {}}, {"type": "tool_use", "id": "d2", "name": "spawn_agent", "input": {}}]}},
        {"type": "assistant", "timestamp": t3.format("09:01:00"), "message": {"id": "c2", "content": [{"type": "text", "text": "Done. All tests pass."}]}},
        {"type": "user", "timestamp": t3.format("09:02:00"), "message": {"content": "wtf, this is still broken!!"}},
        {"type": "assistant", "timestamp": t3.format("09:02:30"), "message": {"id": "c3", "content": [{"type": "tool_use", "id": "d3", "name": "request_user_input", "input": {}}, {"type": "text", "text": "Which option do you prefer?"}]}},
        {"type": "user", "timestamp": t3.format("09:03:00"), "message": {"content": "1. yes\n2. no\n3. B"}},
        {"type": "user", "timestamp": t3.format("09:04:00"), "message": {"content": [{"type": "text", "text": "see [Image #1]"}, {"type": "image"}]}},
        {"type": "user", "timestamp": t3.format("09:05:00"), "message": {"content": "feedback:\n1. the header is too tall and the copy is wrong in three places, please rewrite it fully\n2. the footer links are dead and the colours are off\n3. the form loses state on refresh"}},
    ]], s3, tz, False)
    r3 = s3.row()
    assert r3["agent_dispatches"] == 2 and r3["parallel_dispatch_msgs"] == 1 and r3["max_fanout"] == 2, r3
    assert r3["frustration_msgs"] == 1 and r3["frustration_after"] == {"done_claim": 1}, r3
    assert r3["ask_user_question"] == 1 and r3["agent_behaviors"]["structured_questions"] == 1 and r3["agent_behaviors"]["prose_questions"] == 0, r3["agent_behaviors"]
    assert r3["numbered_answers"] == 1 and r3["messages_with_images"] == 1 and r3["feedback_batches"] == 2, r3
    prog = [{"project": "evalproj", "user_turns": 1, "tool_calls": 0, "subagent_tool_calls": 0, "assistant_turns": 1, "entrypoint": "sdk-cli"} for _ in range(10)]
    prog.append({"project": "evalproj", "user_turns": 8, "tool_calls": 20, "subagent_tool_calls": 0, "assistant_turns": 9, "entrypoint": "cli"})
    normal = [{"project": "app", "user_turns": 1, "tool_calls": 0, "subagent_tool_calls": 0, "assistant_turns": 1, "entrypoint": "cli"} for _ in range(3)]
    assert programmatic_projects(prog + normal) == {"evalproj"}
    assert ZoneInfo(local_tz_name())
    assert looks_like_brief("You are reviewing a repo. Do this.") and looks_like_brief("# A\n# B\n# C\nbody") and looks_like_brief("x" * 3001)
    assert not looks_like_brief("show me the screenshot please") and not looks_like_brief("- a\n- b\n- c")
    assert turn_epoch("2026-01-05T10:00:00Z") == datetime(2026, 1, 5, 10, tzinfo=timezone.utc).timestamp() and turn_epoch(None) is None
    sample = select_sample([
        [("t", "show me the screenshot"), ("t", "show me the page"), ("t", "wtf!! not again")],
        [("t", "show me the diff"), ("t", "please fix the build")],
        [("t", "show me the artifact")],
    ], 2)
    assert [si for si, _t, _x in sample["show me"]] == [0, 1], sample["show me"]
    assert len(sample["frustration"]) == 1 and len(sample["implement or fix"]) == 1, sample
    assert redact_turn("key AKIAABCDEFGHIJKLMNOP   here", 700).startswith("key [redacted]") or "AKIA" not in redact_turn("token sk-abcdefghijklmnopqrstuvwxyz0123456789", 700)
    agg3 = aggregate([s3], tz, 1)
    assert agg3["frustration_msgs"] == 1 and agg3["agent"]["dispatches"] == 2 and agg3["messages_with_images"] == 1, agg3["agent"]
    rep3 = render_report(agg3, [r3], {"generated_at": "", "projects_dir": "", "session_files": 0, "skipped_files": 0, "since_days": None, "excludes": [], "first_start": None, "last_end": None, "scan_seconds": 0, "programmatic": {"projects": 1, "sessions": 10, "user_turns": 10, "tool_calls": 0, "included": False}}, "UTC")
    assert "Frustration signals" in rep3 and "10 sessions, 10 human turns, 1 project(s); excluded" in rep3
    assert r3["moments"] == {"done_not_done": 1, "batch_then_correction": 1}, r3["moments"]
    assert s.models == Counter({"claude-x": 1})
    s4 = Session("t4", "p")
    t4 = "2026-01-07T{}Z"
    tool = lambda mid, tid, at: {"type": "assistant", "timestamp": t4.format(at), "message": {"id": mid, "content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": "pnpm test"}}]}}
    result = lambda tid, at, err=False: {"type": "user", "timestamp": t4.format(at), "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": err, "content": "x"}]}}
    say = lambda mid, at, text: {"type": "assistant", "timestamp": t4.format(at), "message": {"id": mid, "content": [{"type": "text", "text": text}]}}
    ask = lambda at, text, image=False: {"type": "user", "timestamp": t4.format(at), "message": {"content": [{"type": "text", "text": text}] + ([{"type": "image"}] if image else [])}}
    scan_lines([json.dumps(e) for e in [
        ask("09:00:00", "please fix it"),
        tool("f1", "e1", "09:00:10"), result("e1", "09:00:10"),
        tool("f2", "e2", "09:03:00"), result("e2", "09:03:00"),
        say("f3", "09:03:10", "Done, fixed."),
        ask("09:04:00", "what's the status? is it really working?"),
        say("f4", "09:04:30", "Should I also update the docs? Let me know."),
        ask("09:05:00", "1. yes\n2. no"),
        ask("09:06:00", "see [Image #1]", image=True),
        say("f5", "09:06:30", "Done."),
        ask("09:07:00", "[Image #2] still wrong", image=True),
        ask("09:08:00", "- a\n- b\n- c"),
        say("f6", "09:08:30", "ok"),
        ask("09:09:00", "no, wrong"),
        say("f7", "09:09:30", "You need to run the migration manually."),
        ask("09:10:00", "done on my side, I added the key"),
        ask("09:41:00", "where are we?"),
        tool("f8", "e3", "09:41:30"), result("e3", "09:41:30", err=True),
        say("f9", "09:41:40", "Hmm."),
        ask("09:42:00", "wtf!! this sucks"),
        ask("09:43:00", "too long, be more concise"),
    ]], s4, tz, False)
    r4 = s4.row()
    assert r4["moments"] == {"done_not_done": 2, "repeated_correction": 3, "blind_wait": 1, "prose_question_then_numbered_answer": 1, "screenshot_loop": 1,
                             "batch_then_correction": 1, "resumption_then_status_ask": 1, "blocked_then_unblock": 1, "frustrated_after_run_or_error": 1}, r4["moments"]
    assert r4["frustration_msgs"] == 1 and r4["frustration_after"] == {"tool_error": 1} and r4["agent_behaviors"]["long_runs_over_2min"] == 1, r4
    agg4 = aggregate([s4, s3], tz, 1)
    assert agg4["moments"]["done_not_done"] == {"occurrences": 3, "sessions": 2, "cards": "03"}, agg4["moments"]
    assert agg4["moments"]["blind_wait"] == {"occurrences": 1, "sessions": 1, "cards": "01, 10"} and agg4["moments"]["repeated_correction"]["occurrences"] == 3, agg4["moments"]
    rep4 = render_report(agg4, [r4, r3], scope, "UTC")
    assert rep4.index("## Agent behaviors (assistant messages)") < rep4.index("## Moments that point at a use-case") < rep4.index("## Feedback signals (human messages)")
    assert "| blind wait: run over 2 active minutes, then a status ask | 1 | 1 | 01, 10 |" in rep4
    print("self-test ok")


SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|xox[a-z]-[A-Za-z0-9\-]{8,}|gh[pous]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}"
    r"|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}|Bearer\s+\S{16,}|\b\d{8,}:[A-Za-z0-9_\-]{30,}"
    r"|\b[0-9a-f]{32,}\b|[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}|[A-Za-z0-9_\-]{40,})"
)


TURN_SINK = None


def redact_turn(text, max_chars):
    red = " ".join(SECRET_RE.sub("[redacted]", text).split())
    tail = "..." if len(red) > max_chars else ""
    return red[:max_chars] + tail


def emit_turn(n, ts, text, max_chars):
    if TURN_SINK is not None:
        TURN_SINK.append((ts, text))
        return
    print(f"{n:03d} {str(ts or '')[:16]} [{'; '.join(classify_asks(text))}] | {redact_turn(text, max_chars)}")


def select_sample(sessions_turns, per_category):
    picked = defaultdict(list)
    for si, turns in enumerate(sessions_turns):
        seen = Counter()
        for ts, text in turns:
            cats = [classify_asks(text)[0]]
            if is_frustrated(text):
                cats.append("frustration")
            for cat in cats:
                picked[cat].append((seen[cat], si, ts, text))
                seen[cat] += 1
    out = {}
    for cat, items in picked.items():
        items.sort(key=lambda t: (t[0], t[1]))
        out[cat] = [(si, ts, text) for _k, si, ts, text in items[:per_category]]
    return out


BRIEF_MAX_CHARS = 3000
BRIEF_OPENERS = ("you are ", "read and follow", "your task", "## ", "# ")


def turn_epoch(ts):
    if isinstance(ts, datetime):
        return ts.timestamp()
    d = parse_ts(str(ts)) if ts else None
    return d.timestamp() if d else None


def looks_like_brief(text):
    if len(text) > BRIEF_MAX_CHARS:
        return True
    if sum(1 for line in text.splitlines() if line.lstrip().startswith("#")) >= 3:
        return True
    if text.lstrip().lower().startswith(BRIEF_OPENERS):
        return True
    return bool(TRANSCRIPT_RE.search(text))


def sample_user_turns(projects_dir, per_category, max_chars, since_days, codex_dir=None, cursor_dir=None, opencode_dir=None, skip_harnesses=()):
    global TURN_SINK
    matches = [(h, r) for h, r in find_sessions(projects_dir, "", codex_dir or os.path.expanduser("~/.codex"), cursor_dir or CURSOR_USER_DIR, opencode_dir or OPENCODE_DIR) if h not in skip_harnesses]
    cutoff = time.time() - since_days * 86400 if since_days else None
    ordered = []
    for harness, ref in matches:
        if isinstance(ref, str):
            try:
                mtime = os.path.getmtime(ref)
            except OSError:
                continue
            if cutoff and mtime < cutoff:
                continue
            ordered.append((mtime, harness, ref))
        else:
            ordered.append((0, harness, ref))
    ordered.sort(key=lambda t: -t[0])
    printer = {"claude-code": print_claude_user_turns, "codex": print_codex_user_turns, "cursor": print_cursor_user_turns, "opencode": print_opencode_user_turns}
    sessions_turns = []
    scanned = 0
    skipped_briefs = 0
    for _m, harness, ref in ordered:
        TURN_SINK = []
        try:
            printer[harness](ref, max_chars)
        except Exception:
            TURN_SINK = None
            continue
        turns, TURN_SINK = TURN_SINK, None
        scanned += 1
        if cutoff:
            turns = [(ts, text) for ts, text in turns if (turn_epoch(ts) or cutoff) >= cutoff]
        kept = [(ts, text) for ts, text in turns if not looks_like_brief(text)]
        skipped_briefs += len(turns) - len(kept)
        if len(kept) > 1:
            sessions_turns.append(kept)
    sample = select_sample(sessions_turns, per_category)
    total = sum(len(t) for t in sessions_turns)
    for cat in sorted(sample, key=lambda c: -len(sample[c])):
        items = sample[cat]
        print(f"\n## {cat}: {len(items)} of the turns in this category, from {len({si for si, _t, _x in items})} sessions\n")
        for n, (si, ts, text) in enumerate(items, 1):
            print(f"{n:03d} s{si:03d} {str(ts or '')[:16]} | {redact_turn(text, max_chars)}")
    print(f"# sampled from {len(sessions_turns)} sessions with 2+ human turns ({scanned} scanned, {total} turns kept, {skipped_briefs} turns skipped as briefs, pasted transcripts or boilerplate); redacted, stdout only, nothing saved", file=sys.stderr)
    return 0


def find_sessions(projects_dir, sid_prefix, codex_dir, cursor_dir, opencode_dir):
    found = []
    for pdir in os.scandir(projects_dir) if os.path.isdir(projects_dir) else []:
        if pdir.is_dir():
            found += [("claude-code", e.path) for e in os.scandir(pdir.path) if e.is_file() and e.name.endswith(".jsonl") and e.name.startswith(sid_prefix)]
    for sub in ("sessions", "archived_sessions"):
        root = os.path.join(codex_dir, sub)
        for dirpath, _dirs, files in os.walk(root) if os.path.isdir(root) else []:
            found += [("codex", os.path.join(dirpath, f)) for f in files if f.endswith(".jsonl") and sid_prefix in f]
    vscdb = os.path.join(cursor_dir, "globalStorage", "state.vscdb")
    if os.path.isfile(vscdb):
        db = sqlite3.connect(f"file:{vscdb}?mode=ro&immutable=1", uri=True)
        try:
            found += [("cursor", (vscdb, r[0])) for r in db.execute("select composerId from composerHeaders where composerId like ? and not coalesce(isSubagent, 0)", (sid_prefix + "%",))]
        except sqlite3.Error:
            pass
        db.close()
    ocdb = os.path.join(opencode_dir, "opencode.db")
    if os.path.isfile(ocdb):
        con, tmp = sqlite_copy(ocdb)
        try:
            found += [("opencode", (ocdb, r[0])) for r in con.execute("select id from session where id like ? and parent_id is null", (sid_prefix + "%",))]
        except sqlite3.Error:
            pass
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return found


def print_user_turns(projects_dir, sid_prefix, max_chars, codex_dir=None, cursor_dir=None, opencode_dir=None):
    """Stream one session's human turns to stdout with secret-shaped strings redacted.

    Used by the conversation-use-cases skill for its bounded qualitative read:
    the agent reads a handful of sessions this way instead of opening JSONL
    files. Nothing is written to disk.
    """
    matches = find_sessions(projects_dir, sid_prefix, codex_dir or os.path.expanduser("~/.codex"), cursor_dir or CURSOR_USER_DIR, opencode_dir or OPENCODE_DIR)
    if len(matches) != 1:
        print(f"expected exactly one session matching {sid_prefix!r}, found {len(matches)}", file=sys.stderr)
        for h, ref in matches[:10]:
            print(f"  {h} {ref[1] if isinstance(ref, tuple) else os.path.basename(ref)[:-6]}", file=sys.stderr)
        if not matches:
            print("--user-turns reads Claude Code, Codex, Cursor and OpenCode stores; Pi, Droid, Gemini CLI, Amp, Copilot CLI, Goose and Hermes sessions are counted but not readable this way", file=sys.stderr)
        return 2
    harness, ref = matches[0]
    printer = {"claude-code": print_claude_user_turns, "codex": print_codex_user_turns, "cursor": print_cursor_user_turns, "opencode": print_opencode_user_turns}[harness]
    n = printer(ref, max_chars)
    print(f"# {n} human turns, redacted, stdout only", file=sys.stderr)
    return 0


def print_claude_user_turns(path, max_chars):
    n = 0
    for ev in iter_jsonl(path):
        if ev.get("type") != "user" or ev.get("isSidechain"):
            continue
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        text = user_text(msg.get("content"))
        if text is None:
            continue
        origin = ev.get("origin") if isinstance(ev.get("origin"), dict) else {}
        stripped = text.lstrip()
        if ev.get("isMeta") or (origin and origin.get("kind") != "human") or stripped.startswith(SKIP_PREFIXES) or stripped.startswith(INTERRUPT_PREFIX):
            continue
        n += 1
        emit_turn(n, ev.get("timestamp"), text, max_chars)
    return n


def print_cursor_user_turns(ref, max_chars):
    db_path, cid = ref
    db = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    n = 0
    for hdr in (cursor_json(db, f"composerData:{cid}") or {}).get("fullConversationHeadersOnly") or []:
        bub = cursor_json(db, f"bubbleId:{cid}:{hdr.get('bubbleId')}") or {}
        text = cursor_human_text(bub)
        if text is not None:
            n += 1
            emit_turn(n, bub.get("createdAt"), text, max_chars)
    db.close()
    return n


def print_opencode_user_turns(ref, max_chars):
    db_path, sid = ref
    con, tmp = sqlite_copy(db_path)
    n = 0
    try:
        parts = opencode_parts(con, sid)
        for mrow in con.execute("select id, time_created, data from message where session_id=? order by time_created, id", (sid,)):
            try:
                m = json.loads(mrow["data"])
            except Exception:
                continue
            text = opencode_user_text(parts.get(mrow["id"], [])) if m.get("role") == "user" else ""
            if text.strip():
                n += 1
                emit_turn(n, ms_ts(mrow["time_created"]), text, max_chars)
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return n


def codex_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("input_text", "output_text", "text")]
        return "\n".join(parts) if parts else None
    return None


def codex_clean(text):
    text = CODEX_AMBIENT_RE.sub("", text)
    m = CODEX_REQUEST_RE.search(text)
    if m:
        text = m.group(1)
    return text.strip()


def codex_project_label(cwd):
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = cwd[len(home):]
    return cwd.strip("/").replace("/", "-") or "home"


def iter_codex_events(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(ev, dict):
                yield ev


def codex_human_text(ev):
    """Return cleaned human text for a Codex event, or None."""
    pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    t, pt = ev.get("type"), pl.get("type")
    text = None
    if t == "response_item" and pt == "message" and pl.get("role") == "user":
        text = codex_text(pl.get("content"))
    elif t == "event_msg" and pt == "user_message":
        text = pl.get("message") if isinstance(pl.get("message"), str) else codex_text(pl.get("content"))
    if not text:
        return None
    text = codex_clean(text)
    if not text or text.lstrip().startswith("<"):
        return None
    return text


def codex_assistant_text(ev):
    """Return the text of a Codex assistant message event, "" when it has none, or None for other events."""
    pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    t, pt = ev.get("type"), pl.get("type")
    if t == "response_item" and pt == "message" and pl.get("role") == "assistant":
        return codex_text(pl.get("content")) or ""
    if t == "event_msg" and pt == "agent_message":
        return (pl.get("message") if isinstance(pl.get("message"), str) else codex_text(pl.get("content"))) or ""
    return None


def scan_codex_file(path, tz):
    sess = None
    seen = set()
    last_turn = None
    base = os.path.basename(path)[:-6]
    for ev in iter_codex_events(path):
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        t, pt = ev.get("type"), pl.get("type")
        ts = parse_ts(ev.get("timestamp"))
        if sess is None:
            sid = pl.get("id") or pl.get("session_id") or base if t == "session_meta" else base
            cwd = str(pl.get("cwd") or "") if t == "session_meta" else ""
            sess = Session(str(sid), codex_project_label(cwd))
            sess.harness = "codex"
            if t == "session_meta":
                sess.originator = str(pl.get("originator") or pl.get("source") or "")[:30]
                sess.entrypoint = sess.originator
                sess.parent = str(pl.get("parent_thread_id") or "") or None
                if "exec" in (sess.originator or ""):
                    sess.harness = "codex-exec"
                sess.touch(ts)
                continue
        if t == "turn_context":
            if pl.get("model"):
                sess.models[str(pl["model"])[:40]] += 1
            if pl.get("approval_policy"):
                sess.permission_modes[str(pl["approval_policy"])[:20]] += 1
            continue
        text = codex_human_text(ev)
        if text is not None:
            key = (str(ev.get("timestamp", ""))[:16], text[:80])
            if key in seen:
                continue
            seen.add(key)
            images = sum(1 for b in pl["content"] if isinstance(b, dict) and b.get("type") == "input_image") if isinstance(pl.get("content"), list) else 0
            sess.touch(ts)
            sess.human_turn(text, ts, tz, images=images)
            continue
        atext = codex_assistant_text(ev)
        if atext is not None:
            key = ("assistant", str(ev.get("timestamp", ""))[:16], atext[:80])
            if key not in seen:
                seen.add(key)
                sess.assistant_turn(ts, f"assistant-{len(seen)}", False)
                sess.assistant_text(atext, [])
            continue
        if t == "response_item" and pt in ("function_call", "custom_tool_call"):
            sess.tool(pl.get("name"), ts)
        elif t == "event_msg":
            item = pl.get("item") if isinstance(pl.get("item"), dict) else {}
            if pt == "turn_aborted":
                sess.interrupts += 1
            elif pt == "item_completed" and item.get("type") == "UserMessage":
                tid = pl.get("turn_id")
                sess.queued += bool(tid and tid == last_turn)
                last_turn = tid
    return sess


def fold_codex_subagents(found):
    by_id = {s.session_id: s for s in found}
    out = []
    for s in found:
        parent = by_id.get(s.parent) if s.parent else None
        if parent is not None and parent is not s:
            parent.subagent_files += 1
            parent.sub_tool_calls.update(s.tool_calls)
        elif not s.parent:
            out.append(s)
    return out


def discover_codex(codex_dir, since_days, excludes):
    cutoff = time.time() - since_days * 86400 if since_days else None
    found = []
    for sub in ("sessions", "archived_sessions"):
        root = os.path.join(codex_dir, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for f in sorted(files):
                if not f.endswith(".jsonl"):
                    continue
                path = os.path.join(dirpath, f)
                if any(x in path for x in excludes):
                    continue
                if cutoff and os.path.getmtime(path) < cutoff:
                    continue
                found.append(path)
    return found


KNOWN_STORES = [
    ("claude-code", "~/.claude/projects", "parsed"),
    ("codex", "~/.codex/sessions", "parsed; subagent threads folded into their parent"),
    ("codex (archived)", "~/.codex/archived_sessions", "parsed; subagent threads folded into their parent"),
    ("cursor", "~/Library/Application Support/Cursor/User/globalStorage", "parsed (state.vscdb); simulated prompts skipped, cancelled tool calls stand in for interrupts, queue not stored"),
    ("opencode", "~/.local/share/opencode", "parsed (opencode.db), unvalidated on real data; legacy storage/ json not parsed"),
    ("pi", "~/.pi/agent/sessions", "parsed, unvalidated on real data"),
    ("droid", "~/.factory/sessions", "parsed, unvalidated on real data"),
    ("gemini-cli", "~/.gemini/tmp", "parsed, unvalidated on real data"),
    ("amp", "~/.local/share/amp/threads", "parsed, unvalidated; no per-message timestamps"),
    ("copilot-cli", "~/.copilot/session-state", "parsed, unvalidated; community-documented events"),
    ("goose", "~/.local/share/goose/sessions", "parsed (sessions.db), unvalidated on real data"),
    ("hermes", "~/.hermes", "parsed (state.db), unvalidated on real data"),
    ("cline", "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev", "detected only"),
    ("kiro-cli", "~/Library/Application Support/kiro-cli", "detected only"),
    ("kiro-cli (jsonl)", "~/.kiro/sessions", "detected only"),
    ("aider", "~/.aider", "detected only; chat history is per repo (.aider.chat.history.md)"),
    ("conductor", "~/Library/Application Support/com.conductor.app", "detected only; its sessions are Claude Code files already parsed"),
    ("orca", "~/Library/Application Support/Orca", "metadata only; its sessions are Claude Code, Codex or Cursor files"),
    ("chatgpt-desktop", "~/Library/Application Support/com.openai.chat", "encrypted at rest, not readable"),
    ("claude-desktop", "~/Library/Application Support/Claude", "web app cache, not readable"),
]


def discover_stores():
    rows = []
    for name, path, status in KNOWN_STORES:
        full = os.path.expanduser(path)
        if not os.path.exists(full):
            continue
        files, size, newest = 0, 0, 0
        for dirpath, dirs, fs in os.walk(full):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "Cache", "Code Cache", "GPUCache")]
            for f in fs:
                if f.endswith((".jsonl", ".json", ".db", ".vscdb", ".sqlite", ".md", ".data")):
                    files += 1
                    try:
                        st = os.stat(os.path.join(dirpath, f))
                        size += st.st_size
                        newest = max(newest, st.st_mtime)
                    except OSError:
                        pass
        last = datetime.fromtimestamp(newest, tz=timezone.utc).date().isoformat() if newest else "-"
        if name == "opencode" and os.path.isfile(os.path.join(full, "opencode.db")):
            con, tmp = sqlite_copy(os.path.join(full, "opencode.db"))
            try:
                status += f"; {con.execute('select count(*) from session').fetchone()[0]} sessions in db"
            except sqlite3.Error:
                pass
            con.close()
            shutil.rmtree(tmp, ignore_errors=True)
        rows.append((name, path, files, f"{size / 1e6:.1f} MB", last, status))
    print(md_table(["harness", "path", "files", "size", "newest", "status"], rows) if rows else "no known agent stores found")


PARITY_SIGNALS = ("human turns", "interrupts", "queued prompts", "mid-run steering", "tool calls", "subagents", "models",
                  "permission modes", "timestamps", "assistant text", "pasted images", "PR links", "session entrypoint")
BASIC_SIGNALS = ("human turns", "tool calls", "timestamps", "assistant text")
STORE_ABSENT = "store absent on this machine"
SKIPPED_BY_FLAG = "skipped by flag"


def parity_row(*measured, partial=("mid-run steering",)):
    return {s: "measured" if s in measured else "partial" if s in partial else "not measured" for s in PARITY_SIGNALS}


PARITY = {
    "claude-code": parity_row(*BASIC_SIGNALS, "interrupts", "queued prompts", "subagents", "models", "permission modes", "pasted images", "PR links", "session entrypoint"),
    "codex": parity_row(*BASIC_SIGNALS, "interrupts", "queued prompts", "subagents", "models", "permission modes", "pasted images", "session entrypoint"),
    "cursor": parity_row(*BASIC_SIGNALS, "subagents", "models", "pasted images", "session entrypoint", partial=("mid-run steering", "interrupts")),
    "opencode": parity_row(*BASIC_SIGNALS, "interrupts", "subagents", "models", "pasted images", "session entrypoint"),
    "pi": parity_row(*BASIC_SIGNALS, "models"),
    "droid": parity_row(*BASIC_SIGNALS, "models"),
    "gemini-cli": parity_row(*BASIC_SIGNALS, "models"),
    "amp": parity_row("human turns", "tool calls", "assistant text", partial=("mid-run steering", "timestamps")),
    "copilot-cli": parity_row(*BASIC_SIGNALS),
    "goose": parity_row(*BASIC_SIGNALS, partial=("mid-run steering", "models")),
    "hermes": parity_row(*BASIC_SIGNALS, "models"),
}


def stores_present(projects_dir):
    present = {name.split(" ")[0] for name, path, _status in KNOWN_STORES if os.path.exists(os.path.expanduser(path))}
    if os.path.isdir(projects_dir):
        present.add("claude-code")
    return present


def harness_parity(present):
    return {h: {s: v if h in present else STORE_ABSENT for s, v in row.items()} for h, row in PARITY.items()}


def print_codex_user_turns(path, max_chars):
    n = 0
    for ev in iter_codex_events(path):
        text = codex_human_text(ev)
        if text is not None:
            n += 1
            emit_turn(n, ev.get("timestamp"), text, max_chars)
    return n


CURSOR_USER_DIR = os.path.expanduser("~/Library/Application Support/Cursor/User")


def cursor_json(db, key):
    r = db.execute("select value from cursorDiskKV where key=?", (key,)).fetchone()
    try:
        return json.loads(r[0]) if r else None
    except Exception:
        return None


def cursor_human_text(bub):
    text = bub.get("text") or ""
    if bub.get("type") != 1 or bub.get("isSimulatedMsg") or not text.strip():
        return None
    return text


def cursor_workspace_labels(db, user_dir):
    labels = {}
    for wj in glob.glob(os.path.join(user_dir, "workspaceStorage", "*", "workspace.json")):
        try:
            j = json.load(open(wj))
        except Exception:
            continue
        uri = j.get("folder") or j.get("workspace") or ""
        labels[os.path.basename(os.path.dirname(wj))] = codex_project_label(unquote(str(uri).replace("file://", "")))
    try:
        r = db.execute("select value from ItemTable where key='glass.localAgentProjects.v1'").fetchone()
        for proj in (json.loads(r[0]) if r else []):
            ws = proj.get("workspace") or {}
            path = (ws.get("uri") or {}).get("path") or proj.get("name") or ""
            labels.setdefault(ws.get("id"), codex_project_label(str(path)))
    except Exception:
        pass
    return labels


def scan_cursor(since_days, tz, user_dir=CURSOR_USER_DIR):
    """Cursor agent chats live in globalStorage/state.vscdb: composerHeaders (index) and
    cursorDiskKV rows composerData:<id> and bubbleId:<composer>:<bubble>. Bubble type 1 is the
    human, type 2 the assistant; a type 2 bubble with toolFormerData is one tool call. Subagent
    composers (isSubagent=1) are attributed to the parent as subagent tool calls."""
    db_path = os.path.join(user_dir, "globalStorage", "state.vscdb")
    if not os.path.isfile(db_path):
        return []
    cutoff_ms = (time.time() - since_days * 86400) * 1000 if since_days else None
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        db.execute("select 1 from composerHeaders limit 1")
    except sqlite3.Error:
        return []
    labels = cursor_workspace_labels(db, user_dir)
    sessions = {}
    order = []
    rows = db.execute("select composerId, workspaceId, createdAt, lastUpdatedAt, isSubagent, value from composerHeaders").fetchall()
    for cid, wid, created, updated, is_sub, hv in rows:
        if cutoff_ms and updated and updated < cutoff_ms:
            continue
        try:
            head = json.loads(hv) if hv else {}
        except Exception:
            head = {}
        parent = cid
        if is_sub:
            parent = ((head.get("subagentInfo") or {}).get("parentComposerId")) or cid
        sess = sessions.get(parent)
        if sess is None:
            sess = Session(parent, labels.get(wid) or (wid if wid else "(unknown)"))
            sess.harness = "cursor"
            sess.entrypoint = str(head.get("unifiedMode") or "agent")[:20]
            sessions[parent] = sess
            order.append(parent)
        if is_sub:
            sess.subagent_files += 1
        cd = cursor_json(db, f"composerData:{cid}")
        if cd is None:
            continue
        mname = (cd.get("modelConfig") or {}).get("modelName")
        if mname:
            sess.models[str(mname)[:40]] += 1
        for hdr in cd.get("fullConversationHeadersOnly") or []:
            bub = cursor_json(db, f"bubbleId:{cid}:{hdr.get('bubbleId')}")
            if not bub:
                continue
            ts = parse_ts(bub.get("createdAt"))
            if bub.get("type") == 1:
                if is_sub:
                    continue
                text = cursor_human_text(bub)
                if text is None:
                    sess.skipped_user_events += bool(bub.get("isSimulatedMsg"))
                    continue
                images = len((bub.get("context") or {}).get("selectedImages") or [])
                sess.touch(ts)
                sess.human_turn(text, ts, tz, images=images)
            elif bub.get("type") == 2:
                tf = bub.get("toolFormerData")
                if tf:
                    name = str(tf.get("name") or "(unnamed)")[:60]
                    if is_sub:
                        sess.sub_tool_calls[name] += 1
                    else:
                        sess.tool_result(sess.tool(name, ts), tf.get("status") == "error")
                        sess.interrupts += tf.get("status") == "cancelled"
                elif not is_sub:
                    sess.assistant_turn(ts, bub.get("requestId") or hdr.get("bubbleId") or "?", False)
                    sess.assistant_text(bub.get("text"), [])
    db.close()
    return [sessions[k] for k in order]

OPENCODE_DIR = os.path.expanduser("~/.local/share/opencode")


def ms_ts(v):
    try:
        return datetime.fromtimestamp(float(v) / 1000.0, tz=timezone.utc) if v else None
    except (TypeError, ValueError, OSError):
        return None


def any_ts(v):
    if isinstance(v, str):
        return parse_ts(v)
    if isinstance(v, (int, float)):
        return ms_ts(v * (1000 if v < 1e11 else 1))
    return None


def sqlite_copy(db_path):
    tmp = tempfile.mkdtemp(prefix="miner-")
    dst = os.path.join(tmp, os.path.basename(db_path))
    for suf in ("", "-wal", "-shm"):
        if os.path.exists(db_path + suf):
            shutil.copy2(db_path + suf, dst + suf)
    con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con, tmp


def opencode_parts(con, sid):
    parts = defaultdict(list)
    for prow in con.execute("select message_id, data from part where session_id=? order by id", (sid,)):
        try:
            parts[prow["message_id"]].append(json.loads(prow["data"]))
        except Exception:
            continue
    return parts


def opencode_user_text(ps):
    return "\n".join(p.get("text", "") for p in ps if p.get("type") == "text" and not p.get("synthetic"))


def scan_opencode(since_days, tz, root=OPENCODE_DIR):
    """OpenCode keeps sessions in ~/.local/share/opencode/opencode.db (SQLite, WAL): tables
    session, message (data json = Message minus id/sessionID), part (data json = Part minus ids).
    A user message's text is its text parts; an assistant tool call is one part with type "tool"
    and the tool name in part.tool. Child sessions (parent_id set) are subagents and feed the
    parent's subagent buckets. Older builds used storage/{session,message,part}/*.json with
    the same shapes. The db and its WAL are copied to a temp dir and opened read-only so the live
    files are never touched. Not yet validated on a machine with real sessions."""
    out, by_id = [], {}
    db_path = os.path.join(root, "opencode.db")
    cutoff_ms = (time.time() - since_days * 86400) * 1000 if since_days else None
    if not os.path.isfile(db_path):
        return out
    con, tmp = sqlite_copy(db_path)
    try:
        projects = {r["id"]: r["worktree"] for r in con.execute("select id, worktree from project")}
        for srow in con.execute("select * from session order by time_created"):
            if cutoff_ms and srow["time_updated"] and srow["time_updated"] < cutoff_ms:
                continue
            parent = by_id.get(srow["parent_id"]) if srow["parent_id"] else None
            if srow["parent_id"] and parent is None:
                continue
            if parent is not None:
                parent.subagent_files += 1
                sess = parent
            else:
                sess = Session(srow["id"], codex_project_label(str(projects.get(srow["project_id"]) or srow["directory"] or "")))
                sess.harness = "opencode"
                sess.entrypoint = str(srow["agent"] or "")[:20] or None
                sess.touch(ms_ts(srow["time_created"]))
                by_id[srow["id"]] = sess
                out.append(sess)
            parts = opencode_parts(con, srow["id"])
            for mrow in con.execute("select * from message where session_id=? order by time_created, id", (srow["id"],)):
                try:
                    m = json.loads(mrow["data"])
                except Exception:
                    continue
                ts = ms_ts(mrow["time_created"])
                ps = parts.get(mrow["id"], [])
                if parent is not None:
                    if m.get("role") != "user":
                        sess.sub_tool_calls.update(str(p.get("tool") or "(unnamed)")[:60] for p in ps if p.get("type") == "tool")
                elif m.get("role") == "user":
                    text = opencode_user_text(ps)
                    images = sum(1 for p in ps if p.get("type") == "file" and str(p.get("mime") or "").startswith("image/"))
                    if text.strip():
                        sess.touch(ts)
                        sess.human_turn(text, ts, tz, images=images)
                    else:
                        sess.pasted_images += images
                    mdl = m.get("model") or {}
                    if mdl.get("modelID"):
                        sess.models[str(mdl["modelID"])[:40]] += 1
                else:
                    if m.get("modelID"):
                        sess.models[str(m["modelID"])[:40]] += 1
                    if (m.get("error") or {}).get("name") == "MessageAbortedError":
                        sess.interrupts += 1
                    tools = [p for p in ps if p.get("type") == "tool"]
                    names = []
                    for p in tools:
                        names.append(sess.tool(p.get("tool"), ts))
                        sess.tool_result(names[-1], (p.get("state") or {}).get("status") == "error")
                    sess.assistant_turn(ts, mrow["id"], bool(tools))
                    sess.assistant_text("\n".join(p.get("text", "") for p in ps if p.get("type") == "text"), names)
    except sqlite3.Error as e:
        print(f"[opencode] could not read {db_path}: {e}", file=sys.stderr)
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return out

def blocks_text(content):
    """Text of an Anthropic-style content list, or the string itself."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text")]
        return "\n".join(parts) if parts else None
    return None


def blocks_tools(content):
    if not isinstance(content, list):
        return []
    names = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") in ("tool_use", "toolCall", "tool_call", "toolRequest"):
            names.append(b.get("name") or (b.get("toolCall") or {}).get("name") or ((b.get("toolRequest") or {}).get("value") or {}).get("name") or (b.get("function") or {}).get("name") or "(unnamed)")
    return names


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(ev, dict):
                yield ev


def files_under(root, suffixes, since_days):
    cutoff = time.time() - since_days * 86400 if since_days else None
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(suffixes):
                path = os.path.join(dirpath, f)
                if cutoff and os.path.getmtime(path) < cutoff:
                    continue
                yield path


def scan_anthropic_jsonl(root, harness, since_days, tz, header_types=("session", "session_start")):
    """Pi (~/.pi/agent/sessions) and Factory Droid (~/.factory/sessions) both write one JSONL per
    session with a header line and Anthropic-shaped message lines: {type:"message", timestamp,
    message:{role, content}}. Assistant tool calls are content blocks (tool_use or toolCall).
    Written from the documented formats; not validated on real data here."""
    out = []
    if not os.path.isdir(root):
        return out
    for path in files_under(root, (".jsonl",), since_days):
        sess = None
        for ev in iter_jsonl(path):
            t = ev.get("type")
            ts = parse_ts(ev.get("timestamp"))
            if sess is None:
                cwd = str(ev.get("cwd") or "") if t in header_types else ""
                sess = Session(str(ev.get("id") or ev.get("sessionId") or os.path.basename(path)[:-6]), codex_project_label(cwd) if cwd else "(unknown)")
                sess.harness = harness
                sess.touch(ts)
                if t in header_types:
                    continue
            if t != "message":
                continue
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            role = msg.get("role")
            if role == "user":
                text = blocks_text(msg.get("content"))
                if text and text.strip() and not text.lstrip().startswith(SKIP_PREFIXES):
                    sess.touch(ts)
                    sess.human_turn(text, ts, tz)
            elif role == "assistant":
                tools = blocks_tools(msg.get("content"))
                for name in tools:
                    sess.tool(name, ts)
                sess.assistant_turn(ts, ev.get("id") or str(ts), bool(tools))
                sess.assistant_text(blocks_text(msg.get("content")), tools)
                if msg.get("model"):
                    sess.models[str(msg["model"])[:40]] += 1
        if sess is not None and sess.start:
            out.append(sess)
    return out


def scan_gemini(root, since_days, tz):
    """Gemini CLI: ~/.gemini/tmp/<project_hash>/chats/session-*.jsonl (line 1 metadata, then records
    with type user|gemini, timestamp, content, toolCalls[]); older builds wrote one JSON object with a
    messages list. Not validated on real data here."""
    out = []
    if not os.path.isdir(root):
        return out
    for path in files_under(root, (".jsonl", ".json"), since_days):
        if "/chats/" not in path:
            continue
        records, meta = [], {}
        if path.endswith(".jsonl"):
            for ev in iter_jsonl(path):
                if not meta and ev.get("sessionId"):
                    meta = ev
                    continue
                records.append(ev)
        else:
            try:
                obj = json.load(open(path, encoding="utf-8", errors="replace"))
            except Exception:
                continue
            meta = obj if isinstance(obj, dict) else {}
            records = obj.get("messages", []) if isinstance(obj, dict) else []
        if not records:
            continue
        dirs = meta.get("directories") or []
        sess = Session(str(meta.get("sessionId") or os.path.basename(path).rsplit(".", 1)[0]), codex_project_label(str(dirs[0])) if dirs else "(unknown)")
        sess.harness = "gemini-cli"
        sess.touch(parse_ts(meta.get("startTime")))
        for r in records:
            if not isinstance(r, dict):
                continue
            ts = parse_ts(r.get("timestamp"))
            if r.get("type") == "user":
                text = blocks_text(r.get("content")) if not isinstance(r.get("content"), str) else r.get("content")
                if text and text.strip():
                    sess.touch(ts)
                    sess.human_turn(text, ts, tz)
            elif r.get("type") == "gemini":
                calls = r.get("toolCalls") or []
                for c in calls:
                    if isinstance(c, dict):
                        sess.tool(c.get("name"), ts)
                sess.assistant_turn(ts, r.get("id") or str(ts), bool(calls))
                sess.assistant_text(r.get("content") if isinstance(r.get("content"), str) else blocks_text(r.get("content")), [])
                if r.get("model"):
                    sess.models[str(r["model"])[:40]] += 1
        if sess.start:
            out.append(sess)
    return out


def scan_amp(root, since_days, tz):
    """Amp: ~/.local/share/amp/threads/T-*.json, one JSON per thread with created (ms) and
    messages[{role, content[]}]. Messages carry no timestamps, so every turn takes the thread
    time; gaps and hours are not meaningful for Amp. Third-party documented format."""
    out = []
    if not os.path.isdir(root):
        return out
    for path in files_under(root, (".json",), since_days):
        try:
            th = json.load(open(path, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(th, dict) or not isinstance(th.get("messages"), list):
            continue
        ts = ms_ts(th.get("created"))
        sess = Session(str(th.get("id") or os.path.basename(path)[:-5]), "(unknown)")
        sess.harness = "amp"
        sess.touch(ts)
        for i, m in enumerate(th["messages"]):
            if not isinstance(m, dict):
                continue
            if m.get("role") == "user":
                text = blocks_text(m.get("content"))
                if text and text.strip():
                    sess.human_turn(text, ts, tz)
            elif m.get("role") == "assistant":
                tools = blocks_tools(m.get("content"))
                for name in tools:
                    sess.tool(name, ts)
                sess.assistant_turn(ts, str(i), bool(tools))
                sess.assistant_text(blocks_text(m.get("content")), tools)
        if sess.start:
            out.append(sess)
    return out


def scan_copilot(root, since_days, tz):
    """GitHub Copilot CLI: ~/.copilot/session-state/<id>/events.jsonl with {type, timestamp, data};
    user.message, assistant.message, tool.execution_start. Event field names are community
    documented, not an official API."""
    out = []
    if not os.path.isdir(root):
        return out
    for path in files_under(root, ("events.jsonl",), since_days):
        sid = os.path.basename(os.path.dirname(path))
        cwd = ""
        ws = os.path.join(os.path.dirname(path), "workspace.yaml")
        if os.path.isfile(ws):
            for line in open(ws, encoding="utf-8", errors="replace"):
                if line.startswith("cwd:"):
                    cwd = line.split(":", 1)[1].strip().strip('"\'')
                    break
        sess = Session(sid, codex_project_label(cwd) if cwd else "(unknown)")
        sess.harness = "copilot-cli"
        for ev in iter_jsonl(path):
            t = ev.get("type")
            ts = parse_ts(ev.get("timestamp"))
            data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
            if t == "user.message":
                text = data.get("content") or ""
                if text.strip():
                    sess.touch(ts)
                    sess.human_turn(text, ts, tz)
            elif t == "assistant.message":
                sess.assistant_turn(ts, ev.get("id") or str(ts), bool(data.get("toolRequests")))
                sess.assistant_text(data.get("content"), [])
            elif t == "tool.execution_start":
                sess.tool(data.get("toolName") or data.get("name"), ts)
        if sess.start:
            out.append(sess)
    return out


def scan_sqlite_messages(db_path, harness, since_days, tz, sql_sessions, sql_messages, tools_from):
    """Goose (~/.local/share/goose/sessions/sessions.db) and Hermes (~/.hermes/state.db) keep a
    sessions table and a messages table with role and timestamp columns. The db is copied with its
    WAL to a temp dir and opened read-only. Not validated on real data here."""
    out = []
    if not os.path.isfile(db_path):
        return out
    con, tmp = sqlite_copy(db_path)
    try:
        cutoff = time.time() - since_days * 86400 if since_days else None
        for srow in con.execute(sql_sessions):
            start = any_ts(srow["started"])
            if cutoff and start and start.timestamp() < cutoff:
                continue
            sess = Session(str(srow["id"]), codex_project_label(str(srow["cwd"] or "")))
            sess.harness = harness
            if srow["model"]:
                sess.models[str(srow["model"])[:40]] += 1
            sess.touch(start)
            for m in con.execute(sql_messages, (srow["id"],)):
                ts = any_ts(m["ts"])
                role = m["role"]
                if role == "user":
                    text = m["content"] or ""
                    try:
                        text = blocks_text(json.loads(text)) or text if text.lstrip().startswith("[") else text
                    except Exception:
                        pass
                    if isinstance(text, str) and text.strip():
                        sess.touch(ts)
                        sess.human_turn(text, ts, tz)
                elif role == "assistant":
                    names = tools_from(m)
                    for n in names:
                        sess.tool(n, ts)
                    sess.assistant_turn(ts, str(m["mid"]), bool(names))
                    raw = m["content"] or ""
                    try:
                        raw = blocks_text(json.loads(raw)) if raw.lstrip().startswith("[") else raw
                    except Exception:
                        pass
                    sess.assistant_text(raw, names)
            if sess.start:
                out.append(sess)
    except sqlite3.Error as e:
        print(f"[{harness}] could not read {db_path}: {e}", file=sys.stderr)
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return out


GOOSE_SESSIONS_SQL = "select id, working_dir as cwd, created_at as started, provider_name as model from sessions"
GOOSE_MESSAGES_SQL = "select id as mid, role, content_json as content, created_timestamp as ts, NULL as extra from messages where session_id=? order by created_timestamp"


def goose_tools(m):
    try:
        return blocks_tools(json.loads(m["content"]))
    except Exception:
        return []


def hermes_tools(m):
    try:
        calls = json.loads(m["extra"]) if m["extra"] else []
    except Exception:
        return []
    return [((c.get("function") or {}).get("name") or c.get("name") or "(unnamed)") for c in calls if isinstance(c, dict)]


def scan_other_harnesses(since_days, tz):
    found = []
    jobs = [
        ("pi", lambda: scan_anthropic_jsonl(os.path.expanduser(os.environ.get("PI_CODING_AGENT_DIR", "~/.pi/agent")) + "/sessions" if not os.environ.get("PI_CODING_AGENT_DIR") else os.path.join(os.environ["PI_CODING_AGENT_DIR"], "sessions"), "pi", since_days, tz)),
        ("droid", lambda: scan_anthropic_jsonl(os.path.expanduser("~/.factory/sessions"), "droid", since_days, tz)),
        ("gemini-cli", lambda: scan_gemini(os.path.expanduser("~/.gemini/tmp"), since_days, tz)),
        ("amp", lambda: scan_amp(os.path.expanduser("~/.local/share/amp/threads"), since_days, tz)),
        ("copilot-cli", lambda: scan_copilot(os.path.expanduser(os.environ.get("COPILOT_HOME", "~/.copilot")) + "/session-state", since_days, tz)),
        ("goose", lambda: scan_sqlite_messages(os.path.expanduser("~/.local/share/goose/sessions/sessions.db"), "goose", since_days, tz,
            GOOSE_SESSIONS_SQL, GOOSE_MESSAGES_SQL, goose_tools)),
        ("hermes", lambda: scan_sqlite_messages(os.path.expanduser(os.environ.get("HERMES_HOME", "~/.hermes")) + "/state.db", "hermes", since_days, tz,
            "select id, cwd, started_at as started, model from sessions",
            "select id as mid, role, content, timestamp as ts, tool_calls as extra from messages where session_id=? order by timestamp", hermes_tools)),
    ]
    for name, fn in jobs:
        try:
            got = fn()
        except Exception as e:
            print(f"[{name}] skipped: {e}", file=sys.stderr)
            got = []
        if got:
            print(f"[{name}] {len(got)} sessions", file=sys.stderr)
        found.extend(got)
    return found


def self_test_adapters():
    tmp = tempfile.mkdtemp(prefix="miner-selftest-")
    tz = ZoneInfo("UTC")
    try:
        pi_dir = os.path.join(tmp, "pi", "-tmp-proj")
        os.makedirs(pi_dir)
        with open(os.path.join(pi_dir, "s1.jsonl"), "w") as fh:
            fh.write(json.dumps({"type": "session", "id": "pi1", "timestamp": "2026-01-01T10:00:00Z", "cwd": "/tmp/proj"}) + "\n")
            fh.write(json.dumps({"type": "message", "id": "m1", "timestamp": "2026-01-01T10:01:00Z", "message": {"role": "user", "content": "What is the progress? Please be concise."}}) + "\n")
            fh.write(json.dumps({"type": "message", "id": "m2", "timestamp": "2026-01-01T10:02:00Z", "message": {"role": "assistant", "content": [{"type": "toolCall", "name": "bash"}]}}) + "\n")
        got = scan_anthropic_jsonl(os.path.join(tmp, "pi"), "pi", None, tz)
        assert len(got) == 1 and got[0].user_turns == 1 and got[0].tool_calls.get("bash") == 1 and got[0].asks.get("status or steering") == 1, "pi adapter"
        assert len(got[0].assistant_msgs) == 1, "pi assistant turn with tool call"
        g_dir = os.path.join(tmp, "gem", "abc", "chats")
        os.makedirs(g_dir)
        with open(os.path.join(g_dir, "session-1.jsonl"), "w") as fh:
            fh.write(json.dumps({"sessionId": "g1", "startTime": "2026-01-01T10:00:00Z", "directories": ["/tmp/proj"]}) + "\n")
            fh.write(json.dumps({"type": "user", "timestamp": "2026-01-01T10:01:00Z", "content": "fix the failing test"}) + "\n")
            fh.write(json.dumps({"type": "gemini", "timestamp": "2026-01-01T10:02:00Z", "toolCalls": [{"name": "run_shell_command"}]}) + "\n")
        got = scan_gemini(os.path.join(tmp, "gem"), None, tz)
        assert len(got) == 1 and got[0].user_turns == 1 and got[0].tool_calls.get("run_shell_command") == 1 and len(got[0].assistant_msgs) == 1, "gemini adapter"
        amp_dir = os.path.join(tmp, "amp")
        os.makedirs(amp_dir)
        json.dump({"id": "T-1", "created": 1767261600000, "messages": [{"role": "user", "content": [{"type": "text", "text": "review this PR"}]}, {"role": "assistant", "content": [{"type": "tool_use", "name": "Read"}]}]}, open(os.path.join(amp_dir, "T-1.json"), "w"))
        got = scan_amp(amp_dir, None, tz)
        assert len(got) == 1 and got[0].user_turns == 1 and got[0].tool_calls.get("Read") == 1 and len(got[0].assistant_msgs) == 1, "amp adapter"
        print("adapter self-test ok", file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def self_test_stores():
    import contextlib
    import io
    tmp = tempfile.mkdtemp(prefix="miner-selftest-")
    tz = ZoneInfo("UTC")
    ts = "2026-01-01T10:0{}:00Z"
    try:
        cx = os.path.join(tmp, "codex", "sessions")
        os.makedirs(cx)
        with open(os.path.join(cx, "rollout-cx-parent.jsonl"), "w") as fh:
            for ev in [
                {"type": "session_meta", "timestamp": ts.format(0), "payload": {"id": "cx-parent", "cwd": "/tmp/p", "originator": "codex-tui"}},
                {"type": "turn_context", "timestamp": ts.format(0), "payload": {"model": "gpt-x", "approval_policy": "never"}},
                {"type": "event_msg", "timestamp": ts.format(1), "payload": {"type": "task_started", "turn_id": "t1"}},
                {"type": "response_item", "timestamp": ts.format(1), "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "fix the bug"}, {"type": "input_image", "image_url": "x"}]}},
                {"type": "event_msg", "timestamp": ts.format(1), "payload": {"type": "item_completed", "turn_id": "t1", "item": {"type": "UserMessage"}}},
                {"type": "response_item", "timestamp": ts.format(1), "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done, fixed."}]}},
                {"type": "event_msg", "timestamp": ts.format(1), "payload": {"type": "agent_message", "message": "Done, fixed."}},
                {"type": "response_item", "timestamp": ts.format(2), "payload": {"type": "function_call", "name": "exec"}},
                {"type": "response_item", "timestamp": ts.format(3), "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "also run the tests"}]}},
                {"type": "event_msg", "timestamp": ts.format(3), "payload": {"type": "item_completed", "turn_id": "t1", "item": {"type": "UserMessage"}}},
                {"type": "event_msg", "timestamp": ts.format(4), "payload": {"type": "turn_aborted", "turn_id": "t1", "reason": "interrupted"}},
            ]:
                fh.write(json.dumps(ev) + "\n")
        with open(os.path.join(cx, "rollout-cx-child.jsonl"), "w") as fh:
            for ev in [
                {"type": "session_meta", "timestamp": ts.format(2), "payload": {"id": "cx-child", "cwd": "/tmp/p", "originator": "codex-tui", "parent_thread_id": "cx-parent"}},
                {"type": "response_item", "timestamp": ts.format(2), "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "subtask"}]}},
                {"type": "response_item", "timestamp": ts.format(2), "payload": {"type": "function_call", "name": "apply_patch"}},
            ]:
                fh.write(json.dumps(ev) + "\n")
        got = fold_codex_subagents([scan_codex_file(p, tz) for p in discover_codex(os.path.join(tmp, "codex"), None, [])])
        assert len(got) == 1, "codex fold"
        c = got[0]
        assert c.user_turns == 2 and c.queued == 1 and c.steer == 1 and c.interrupts == 1 and c.pasted_images == 1, "codex signals"
        assert len(c.assistant_msgs) == 1 and c.agent_sig["assistant_text_msgs"] == 1 and c.agent_sig["done_claims"] == 1, "codex assistant dedup"
        assert c.models == Counter({"gpt-x": 1}) and c.permission_modes == Counter({"never": 1}), "codex model and permission"
        assert c.subagent_files == 1 and c.sub_tool_calls == Counter({"apply_patch": 1}) and c.tool_calls == Counter({"exec": 1}), "codex subagent"

        cu = os.path.join(tmp, "cursor", "globalStorage")
        os.makedirs(cu)
        db = sqlite3.connect(os.path.join(cu, "state.vscdb"))
        db.execute("create table composerHeaders(composerId, workspaceId, createdAt, lastUpdatedAt, isArchived, isSubagent, recency, checkpointAt, value)")
        db.execute("create table cursorDiskKV(key, value)")
        db.execute("insert into composerHeaders values ('cu-1', 'w1', 1, 1, 0, 0, 0, 0, ?)", (json.dumps({"unifiedMode": "agent"}),))
        db.execute("insert into composerHeaders values ('cu-sub', 'w1', 1, 1, 0, 1, 0, 0, ?)", (json.dumps({"subagentInfo": {"parentComposerId": "cu-1"}}),))
        kv = [
            ("composerData:cu-1", {"modelConfig": {"modelName": "m1"}, "fullConversationHeadersOnly": [{"bubbleId": f"b{i}"} for i in range(1, 5)]}),
            ("bubbleId:cu-1:b1", {"type": 1, "createdAt": ts.format(0), "text": "review the screenshot", "context": {"selectedImages": [{"uuid": "i"}]}}),
            ("bubbleId:cu-1:b2", {"type": 2, "createdAt": ts.format(1), "toolFormerData": {"name": "read_file", "status": "cancelled"}}),
            ("bubbleId:cu-1:b3", {"type": 1, "createdAt": ts.format(2), "text": "continue", "isSimulatedMsg": True}),
            ("bubbleId:cu-1:b4", {"type": 2, "createdAt": ts.format(3), "text": "done"}),
            ("composerData:cu-sub", {"fullConversationHeadersOnly": [{"bubbleId": "s1"}]}),
            ("bubbleId:cu-sub:s1", {"type": 2, "createdAt": ts.format(1), "toolFormerData": {"name": "grep", "status": "completed"}}),
        ]
        db.executemany("insert into cursorDiskKV values (?, ?)", [(k, json.dumps(v)) for k, v in kv])
        db.commit()
        db.close()
        got = scan_cursor(None, tz, user_dir=os.path.join(tmp, "cursor"))
        assert len(got) == 1, "cursor sessions"
        c = got[0]
        assert c.user_turns == 1 and c.skipped_user_events == 1 and c.interrupts == 1 and c.pasted_images == 1 and c.steer == 0, "cursor signals"
        assert c.tool_calls == Counter({"read_file": 1}) and c.sub_tool_calls == Counter({"grep": 1}) and c.subagent_files == 1 and c.models == Counter({"m1": 1}), ("cursor tools", dict(c.tool_calls), dict(c.sub_tool_calls), c.subagent_files, dict(c.models))

        oc = os.path.join(tmp, "opencode")
        os.makedirs(oc)
        db = sqlite3.connect(os.path.join(oc, "opencode.db"))
        db.execute("create table project(id, worktree)")
        db.execute("create table session(id, project_id, parent_id, directory, agent, time_created, time_updated)")
        db.execute("create table message(id, session_id, time_created, data)")
        db.execute("create table part(id, message_id, session_id, data)")
        db.execute("insert into project values ('p1', '/tmp/p')")
        t0 = 1767261600000
        db.execute("insert into session values ('oc-1', 'p1', NULL, '/tmp/p', 'build', ?, ?)", (t0, t0))
        db.execute("insert into session values ('oc-1-child', 'p1', 'oc-1', '/tmp/p', 'general', ?, ?)", (t0 + 1000, t0 + 1000))
        db.executemany("insert into message values (?, ?, ?, ?)", [
            ("m1", "oc-1", t0, json.dumps({"role": "user", "model": {"modelID": "mx"}})),
            ("m2", "oc-1", t0 + 500, json.dumps({"role": "assistant", "modelID": "mx", "error": {"name": "MessageAbortedError"}})),
            ("m3", "oc-1-child", t0 + 1000, json.dumps({"role": "assistant", "modelID": "mx"})),
        ])
        db.executemany("insert into part values (?, ?, ?, ?)", [
            ("p1", "m1", "oc-1", json.dumps({"type": "text", "text": "deploy it"})),
            ("p2", "m1", "oc-1", json.dumps({"type": "file", "mime": "image/png"})),
            ("p3", "m2", "oc-1", json.dumps({"type": "tool", "tool": "bash"})),
            ("p4", "m3", "oc-1-child", json.dumps({"type": "tool", "tool": "read"})),
        ])
        db.commit()
        db.close()
        got = scan_opencode(None, tz, root=oc)
        assert len(got) == 1, "opencode sessions"
        o = got[0]
        assert o.user_turns == 1 and o.interrupts == 1 and o.pasted_images == 1 and o.tool_calls == Counter({"bash": 1}), "opencode signals"
        assert o.subagent_files == 1 and o.sub_tool_calls == Counter({"read": 1}) and o.models == Counter({"mx": 2}), "opencode subagent"
        assert len(o.assistant_msgs) == 1, "opencode assistant turn with tool call"

        gs = os.path.join(tmp, "goose")
        os.makedirs(gs)
        db = sqlite3.connect(os.path.join(gs, "sessions.db"))
        db.execute("create table sessions(id, working_dir, created_at, provider_name)")
        db.execute("create table messages(id, session_id, role, content_json, created_timestamp)")
        db.execute("insert into sessions values ('g1', '/tmp/p', NULL, 'prov')")
        db.executemany("insert into messages values (?, ?, ?, ?, ?)", [
            (1, "g1", "user", json.dumps([{"type": "text", "text": "run the tests"}]), 1767261600),
            (2, "g1", "assistant", json.dumps([{"type": "toolRequest", "toolRequest": {"value": {"name": "shell"}}}]), None),
        ])
        db.commit()
        db.close()
        got = scan_sqlite_messages(os.path.join(gs, "sessions.db"), "goose", None, tz, GOOSE_SESSIONS_SQL, GOOSE_MESSAGES_SQL, goose_tools)
        assert len(got) == 1 and got[0].user_turns == 1 and got[0].tool_calls == Counter({"shell": 1}) and len(got[0].assistant_msgs) == 1, "goose null timestamps"

        for prefix, expected in (("cx-par", 2), ("cu-", 1), ("oc-", 1)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                rc = print_user_turns(os.path.join(tmp, "none"), prefix, 40, os.path.join(tmp, "codex"), os.path.join(tmp, "cursor"), oc)
            assert rc == 0 and len(buf.getvalue().splitlines()) == expected, ("user-turns", prefix)
        print("store self-test ok", file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--since-days", type=int, default=None, help="only files modified in the last N days")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--exclude", action="append", default=[], help="skip files whose path contains this (repeatable)")
    ap.add_argument("--tz", default=None, help="IANA zone for hours of day; defaults to this machine's zone")
    ap.add_argument("--include-programmatic", action="store_true", help="keep one-shot harness sessions in the counts")
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--notes", default=None, help="markdown file appended verbatim to the report")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--discover", action="store_true", help="list known agent stores present on this machine and exit")
    ap.add_argument("--codex-dir", default=os.path.expanduser("~/.codex"))
    ap.add_argument("--no-codex", action="store_true", help="skip Codex threads")
    ap.add_argument("--no-cursor", action="store_true", help="skip Cursor agent chats")
    ap.add_argument("--no-opencode", action="store_true", help="skip OpenCode sessions")
    ap.add_argument("--no-other", action="store_true", help="skip Pi, Droid, Gemini CLI, Amp, Copilot CLI, Goose, Hermes")
    ap.add_argument("--user-turns", metavar="SESSION_ID", default=None,
                    help="print one session's human turns (redacted) to stdout and exit; id prefix allowed")
    ap.add_argument("--max-chars", type=int, default=700, help="truncate each printed turn (with --user-turns or --sample-turns)")
    ap.add_argument("--sample-turns", metavar="N", type=int, default=None,
                    help="stream up to N redacted human turns per ask category, drawn across all readable sessions (plus N with frustration markers), then exit")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        self_test_adapters()
        self_test_stores()
        return
    if args.user_turns:
        sys.exit(print_user_turns(args.projects_dir, args.user_turns, args.max_chars, args.codex_dir))
    if args.sample_turns:
        skip = tuple(h for h, off in (("codex", args.no_codex), ("cursor", args.no_cursor), ("opencode", args.no_opencode)) if off)
        sys.exit(sample_user_turns(args.projects_dir, args.sample_turns, args.max_chars, args.since_days, args.codex_dir, skip_harnesses=skip))
    if args.discover:
        discover_stores()
        return
    tz_name = args.tz or local_tz_name()
    tz = ZoneInfo(tz_name)
    t0 = time.time()
    found, skipped = discover(args.projects_dir, args.since_days, args.exclude)
    sessions = []
    for i, (project, sid, main, subs) in enumerate(found, 1):
        s = Session(sid, project)
        scan_file(main, s, tz, False)
        for sub in subs:
            s.subagent_files += 1
            scan_file(sub, s, tz, True)
        sessions.append(s)
        print(f"[{i}/{len(found)}] {project} {sid[:8]} turns={s.user_turns} subagents={len(subs)}", file=sys.stderr)
    codex_files = []
    if not args.no_codex and os.path.isdir(args.codex_dir):
        codex_files = discover_codex(args.codex_dir, args.since_days, args.exclude)
        codex_sessions = []
        for i, path in enumerate(codex_files, 1):
            s = scan_codex_file(path, tz)
            if s is not None:
                codex_sessions.append(s)
            print(f"[codex {i}/{len(codex_files)}] {os.path.basename(path)[:40]} turns={s.user_turns if s else 0}", file=sys.stderr)
        top = fold_codex_subagents(codex_sessions)
        sessions.extend(top)
        print(f"[codex] {len(codex_sessions) - len(top)} subagent threads folded into parents or dropped", file=sys.stderr)
    cursor_sessions = []
    if not args.no_cursor:
        cursor_sessions = scan_cursor(args.since_days, tz)
        sessions.extend(cursor_sessions)
        print(f"[cursor] {len(cursor_sessions)} agent chats", file=sys.stderr)
    opencode_sessions = []
    if not args.no_opencode:
        opencode_sessions = scan_opencode(args.since_days, tz)
        sessions.extend(opencode_sessions)
        print(f"[opencode] {len(opencode_sessions)} sessions", file=sys.stderr)
    other = [] if args.no_other else scan_other_harnesses(args.since_days, tz)
    sessions.extend(other)
    sessions = [s for s in sessions if s.start]
    sessions.sort(key=lambda s: s.start)
    prog_projects = programmatic_projects([s.row() for s in sessions])
    prog_sessions = [s for s in sessions if s.project in prog_projects]
    programmatic = {"projects": len(prog_projects), "sessions": len(prog_sessions),
                    "user_turns": sum(s.user_turns for s in prog_sessions),
                    "tool_calls": sum(sum(s.tool_calls.values()) for s in prog_sessions),
                    "included": bool(args.include_programmatic)}
    if prog_sessions and not args.include_programmatic:
        sessions = [s for s in sessions if s.project not in prog_projects]
        print(f"[programmatic] {len(prog_sessions)} one-shot sessions in {len(prog_projects)} harness project(s) excluded; --include-programmatic keeps them", file=sys.stderr)
    rows = [s.row() for s in sessions]
    agg = aggregate(sessions, tz, args.weeks)
    scope = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "projects_dir": args.projects_dir,
        "session_files": len(found),
        "codex_files": len(codex_files),
        "cursor_sessions": len(cursor_sessions),
        "opencode_sessions": len(opencode_sessions),
        "skipped_files": len(skipped),
        "skipped_reasons": dict(Counter(reason for _p, reason in skipped)),
        "since_days": args.since_days,
        "excludes": args.exclude,
        "first_start": rows[0]["start"] if rows else None,
        "last_end": max((r["end"] for r in rows if r["end"]), default=None),
        "scan_seconds": round(time.time() - t0, 1),
        "programmatic": programmatic,
        "tz": tz_name,
    }
    parity = harness_parity(stores_present(args.projects_dir))
    others = ("pi", "droid", "gemini-cli", "amp", "copilot-cli", "goose", "hermes")
    for h, off in (("codex", args.no_codex), ("cursor", args.no_cursor), ("opencode", args.no_opencode)) + tuple((h, args.no_other) for h in others):
        if off and parity[h]["human turns"] != STORE_ABSENT:
            parity[h] = {sig: SKIPPED_BY_FLAG for sig in PARITY_SIGNALS}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "session_miner_output.json"), "w") as fh:
        json.dump({"scope": scope, "aggregates": agg, "sessions": rows, "harness_parity": parity}, fh, indent=1, default=str)
    report = render_report(agg, rows, scope, tz_name, parity)
    if args.notes and os.path.isfile(args.notes):
        with open(args.notes) as fh:
            report += "\n" + fh.read()
    with open(os.path.join(args.out, "session_miner_report.md"), "w") as fh:
        fh.write(report)
    print(f"done: {len(rows)} sessions in {scope['scan_seconds']}s -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
