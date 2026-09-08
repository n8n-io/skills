#!/usr/bin/env python3
"""Quantitative, privacy-preserving miner for local agent transcripts.

Reads every Claude Code session under a projects directory (default
~/.claude/projects), plus Codex CLI threads under ~/.codex and Cursor agent chats from its
state.vscdb, and emits counts only: no message text, no file paths,
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

Usage:
    python3 session_miner.py --out DIR [--projects-dir P] [--since-days N]
                             [--exclude ID ...] [--tz Europe/Lisbon]
                             [--weeks 12] [--notes FILE] [--self-test]

Writes DIR/session_miner_output.json and DIR/session_miner_report.md.
--since-days filters files by mtime. --exclude drops any file whose path
contains the given string (session id, project dir, ...). --notes appends a
markdown file verbatim to the end of the report.
"""

import argparse
import sqlite3
import glob
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
    ("status or steering", re.compile(r"\b(progress|status|what'?s missing|where are we|did we|have you|are you sure|what do you need|continue|go on|stop|wait)\b", re.I)),
    ("approve or hand back", re.compile(r"^\s*(yes|ok|okay|go ahead|approved|lgtm|proceed|merged|deployed|done)\b", re.I)),
    ("answer questions", re.compile(r"(?m)^\s*(Q\d+|[A-D]\d*|\d+)\s*[:.)-]", re.I)),
    ("feedback or correction", re.compile(r"\b(no,|not what|wrong|instead|should have|I do not want|I don't want|remove|too long|concise|again|fix this|does not work|doesn't work|not great|not good)\b", re.I)),
    ("implement or fix", re.compile(r"\b(implement|build|add|create|fix|refactor|migrate|update the code|write the code|make it work|feature|bug|failing)\b", re.I)),
    ("review or verify", re.compile(r"\b(review|verify|test it|check (the|that|if)|validate|audit|qa\b|screenshots?)", re.I)),
    ("plan or design", re.compile(r"\b(plan|design|brainstorm|architecture|spec|approach|options|tradeoffs?|grill)\b", re.I)),
    ("research or explain", re.compile(r"\b(research|investigate|explain|why (is|does|did)|how (does|do|is)|compare|find out|look into|what is)\b", re.I)),
    ("docs or writing", re.compile(r"\b(doc|document|write up|write a|readme|notion page|article|summary|brief|report)\b", re.I)),
    ("analytics or data", re.compile(r"\b(sql|query|bigquery|dashboard|metric|conversion|funnel|chart|posthog|analytics)\b", re.I)),
    ("ops or deploy", re.compile(r"\b(deploy|release|tag|docker|server|restart|ci\b|pipeline|prod|cloudflare|vercel)\b", re.I)),
    ("comms or drafts", re.compile(r"\b(slack|message to|reply to|email|draft|announce|dm\b|post in)\b", re.I)),
    ("tickets or tracking", re.compile(r"\b(linear|issue|ticket|todo|task list|backlog)\b", re.I)),
]


def classify_ask(text):
    for label, rx in ASK_RE:
        if rx.search(text):
            return label
    return "other"
CODEX_AMBIENT_RE = re.compile(r"<(in-app-browser-context|environment_context|permissions_instructions|skills_instructions|user_instructions)[^>]*>.*?</\1>", re.S)
CODEX_REQUEST_RE = re.compile(r"## My request for Codex:\s*(.*)", re.S)
INTERRUPT_PREFIX = "[Request interrupted"
TYPE_RE = re.compile(r'"type"\s*:\s*"(user|assistant|pr-link)"')
MCP_RE = re.compile(r"^mcp__(.+?)__(.+)$")
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEGMENT_RE = re.compile(r"^(?:[^\n;&|]|&(?!&)|\|(?!\|))*?(?:&&|\|\||;|\n)\s*")
SETUP_HEADS = {"cd", "export", "set", "source", ".", "nvm", "unset", "ulimit", "pushd"}
WRAPPERS = {"sudo", "command", "exec", "time", "nohup", "env"}
ACTIVE_GAP_CAP_S = 900
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

FEEDBACK = {
    "numbered_answers": [r"(?m)^Q\d+\s*[:.\-]"],
    "corrections": [
        r"\bno,", r"\bnot what\b", r"\bI do not want\b", r"\bI don'?t want\b", r"\bwrong\b",
        r"\bagain\b", r"\byou should\b", r"\bbe more concise\b", r"\btoo long\b", r"\bremove\b",
    ],
    "status_asks": [r"\bprogress\b", r"\bstatus\b", r"\bwhere are we\b", r"\bdid we\b", r"\bhave you\b"],
    "approvals": [r"\byes\b", r"\bok\b", r"\bgo ahead\b", r"\bapproved\b", r"\blgtm\b", r"\bproceed\b"],
    "visual_requests": [
        r"\bartifact", r"\bscreenshot", r"\bmockup", r"\bdiagram", r"\bprototype",
        r"\bcollapsible\b", r"\bdashboard",
    ],
}
FEEDBACK_RE = {
    cat: [(p, re.compile(p, re.IGNORECASE)) for p in pats] for cat, pats in FEEDBACK.items()
}


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
        m = MCP_RE.match(name)
        if m:
            self.mcp[(m.group(1), m.group(2))] += 1
        elif name == "Skill":
            self.skills[str(inp.get("skill") or "(unknown)")[:60]] += 1
        elif name == "Agent":
            self.agent_types[str(inp.get("subagent_type") or "(default)")[:40]] += 1
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
            self.assistant_msgs.add(msg_id)
            self.touch(parse_ts(ev.get("timestamp")))
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                self.on_tool_use(block, msg_id, sidechain)
            if not sidechain:
                self.last_assistant_block = block.get("type")

    def on_user(self, ev, sidechain, tz):
        if sidechain:
            return
        ts = parse_ts(ev.get("timestamp"))
        self.touch(ts)
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        text = user_text(msg.get("content"))
        if text is None:
            return
        origin = ev.get("origin") if isinstance(ev.get("origin"), dict) else {}
        stripped = text.lstrip()
        if ev.get("isMeta") or (origin and origin.get("kind") != "human") or stripped.startswith(SKIP_PREFIXES):
            self.skipped_user_events += 1
            return
        if stripped.startswith(INTERRUPT_PREFIX):
            self.interrupts += 1
            return
        if isinstance(msg.get("content"), list):
            self.pasted_images += sum(1 for b in msg["content"] if isinstance(b, dict) and b.get("type") == "image")
        self.human_turn(text, ts, tz, ev.get("promptSource") == "queued")

    def human_turn(self, text, ts, tz, queued=False):
        """Account one human turn. Shared by every harness adapter."""
        self.user_turns += 1
        self.msg_lens.append(len(text))
        words = len(text.split())
        if words < 15:
            self.words_short += 1
        if words > 100:
            self.words_long += 1
        self.pasted_images += len(IMAGE_RE.findall(text))
        self.secret_like += len(SECRET_RE.findall(text))
        self.asks[classify_ask(text)] += 1
        if ts is not None:
            if self.turn_ts and ts > self.turn_ts[-1]:
                self.longest_gap_s = max(self.longest_gap_s, (ts - self.turn_ts[-1]).total_seconds())
            self.turn_ts.append(ts)
            self.turn_hours[ts.astimezone(tz).hour] += 1
        if queued:
            self.queued += 1
        if self.last_assistant_block == "tool_use":
            self.steer += 1
        self.last_assistant_block = None
        for cat, pats in FEEDBACK_RE.items():
            hit = False
            for pat, rx in pats:
                n = len(rx.findall(text))
                if n:
                    hit = True
                    self.markers[(cat, pat)] += n
            if hit:
                self.feedback[cat] += 1

    def assistant_turn(self, ts, msg_id, had_tool):
        self.assistant_msgs.add(msg_id)
        self.touch(ts)
        self.last_assistant_block = "tool_use" if had_tool else "text"

    def tool(self, name, ts):
        name = str(name or "(unnamed)")[:60]
        self.tool_calls[name] += 1
        self.touch(ts)
        self.last_assistant_block = "tool_use"
        m = MCP_RE.match(name)
        if m:
            self.mcp[(m.group(1), m.group(2))] += 1

    def gaps(self):
        ts = sorted(self.turn_ts)
        return [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]

    def row(self):
        dur = (self.end - self.start).total_seconds() / 60 if self.start and self.end else None
        gaps = self.gaps()
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
            "agent_dispatches": self.tool_calls.get("Agent", 0),
            "parallel_dispatch_msgs": sum(1 for v in self.agent_per_msg.values() if v >= 2),
            "max_fanout": max(self.agent_per_msg.values(), default=0),
            "skill_calls": self.tool_calls.get("Skill", 0),
            "artifact_calls": self.tool_calls.get("Artifact", 0),
            "ask_user_question": self.tool_calls.get("AskUserQuestion", 0),
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
            "words_short": self.words_short,
            "words_long": self.words_long,
            "pr_links": self.pr_links,
            "longest_gap_min": round(self.longest_gap_s / 60, 1),
            "asks": dict(self.asks.most_common()),
            "models": dict(self.models.most_common(5)),
            "permission_modes": dict(self.permission_modes.most_common(5)),
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


def aggregate(sessions, tz, weeks):
    agg = {
        "sessions": len(sessions),
        "user_turns": 0, "assistant_turns": 0, "tool_calls": 0, "subagent_files": 0,
        "subagent_tool_calls": 0, "interrupts": 0, "queued_prompts": 0, "mid_run_steering": 0,
        "sessions_with_parallel_dispatch": 0, "parallel_dispatch_msgs": 0, "skipped_user_events": 0,
        "bad_lines": 0, "secret_like": 0, "pasted_images": 0, "words_short": 0, "words_long": 0, "pr_links": 0,
    }
    per_harness, models, perms, asks = Counter(), Counter(), Counter(), Counter()
    longest_gap = 0.0
    tools, sub_tools, mcp, skills, agent_types = Counter(), Counter(), Counter(), Counter(), Counter()
    artifact, bash, feedback, markers = Counter(), Counter(), Counter(), Counter()
    edits = defaultdict(Counter)
    lens, gaps, durations, actives = [], [], [], []
    hours_start, hours_turns, weekly, per_project, per_entry = Counter(), Counter(), Counter(), Counter(), Counter()
    dead_starts = 0
    now = datetime.now(timezone.utc).astimezone(tz)
    this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_starts = [this_monday - timedelta(weeks=k) for k in range(weeks - 1, -1, -1)]
    for s in sessions:
        r = s.row()
        for k in ("user_turns", "assistant_turns", "tool_calls", "subagent_files", "subagent_tool_calls",
                  "interrupts", "queued_prompts", "mid_run_steering", "parallel_dispatch_msgs",
                  "skipped_user_events", "bad_lines", "secret_like", "pasted_images", "words_short",
                  "words_long", "pr_links"):
            agg[k] += r[k]
        per_harness[s.harness] += 1
        models.update(s.models)
        perms.update(s.permission_modes)
        asks.update(s.asks)
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
        hours_turns.update(s.turn_hours)
        per_project[s.project] += 1
        per_entry[r["entrypoint"] or "(unknown)"] += 1
        actives.append(r["active_min"])
        dead_starts += 1 if r["user_turns"] and not r["assistant_turns"] else 0
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
            srv: {"total": sum(c.values()), "top_tools": dict(c.most_common(5))}
            for srv, c in sorted(mcp_servers.items(), key=lambda kv: -sum(kv[1].values()))
        },
        "skills": dict(skills.most_common()),
        "agent": {
            "dispatches": tools.get("Agent", 0),
            "parallel_dispatch_msgs": agg["parallel_dispatch_msgs"],
            "sessions_with_parallel_dispatch": agg["sessions_with_parallel_dispatch"],
            "max_fanout": max((s.row()["max_fanout"] for s in sessions), default=0),
            "subagent_types": dict(agent_types.most_common()),
        },
        "artifact_actions": dict(artifact.most_common()),
        "ask_user_question": tools.get("AskUserQuestion", 0),
        "edits_by_ext": {t: dict(c.most_common()) for t, c in edits.items()},
        "bash_top25": dict(bash.most_common(25)),
        "feedback_messages": dict(feedback.most_common()),
        "feedback_markers": {f"{cat}: {pat}": n for (cat, pat), n in markers.most_common()},
        "user_msg_chars": {"count": len(lens), "median": pct(lens, 50), "p90": pct(lens, 90)},
        "turn_gap_seconds": {"count": len(gaps), "median": pct(gaps, 50), "p90": pct(gaps, 90)},
        "weekly_sessions": {ws.date().isoformat(): weekly.get(ws.date().isoformat(), 0) for ws in week_starts},
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


def render_report(agg, rows, scope, tz_name):
    L = []
    L.append("# Agent session miner report\n")
    L.append(f"Generated {scope['generated_at']}. Timezone for hours: {tz_name}. Counts only, no message text.\n")
    L.append("## Scope\n")
    L.append(md_table(["metric", "value"], [
        ("projects dir", scope["projects_dir"]),
        ("Claude Code session files", scope["session_files"]),
        ("Codex thread files", scope.get("codex_files", 0)),
        ("Cursor agent chats", scope.get("cursor_sessions", 0)),
        ("subagent files", agg["subagent_files"]),
        ("skipped files", scope["skipped_files"]),
        ("since days", scope["since_days"] or "all"),
        ("excludes", ", ".join(scope["excludes"]) or "none"),
        ("first session start", scope["first_start"]),
        ("last session end", scope["last_end"]),
        ("malformed lines", agg["bad_lines"]),
        ("scan seconds", scope["scan_seconds"]),
    ]))
    L.append("\n## Session inventory\n")
    L.append(md_table(["metric", "value"], [
        ("sessions", agg["sessions"]),
        ("human user turns", agg["user_turns"]),
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
        ("PR links recorded by the harness", agg["pr_links"]),
        ("secret-shaped or long identifier-like strings in human text (count only; check and rotate real ones)", agg["secret_like"]),
        ("permission modes seen", ", ".join(f"{k} ({v})" for k, v in agg["permission_modes"].items()) or "not recorded"),
        ("models seen (Codex threads record these)", ", ".join(f"{k} ({v})" for k, v in agg["models"].items()) or "not recorded"),
    ]))
    L.append("\n### What the human turns ask for (first matching category, counts only)\n")
    L.append(counter_table(agg["asks"], "ask", "human turns"))
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
    L.append("\n### Subagents, top 15\n")
    L.append(counter_table(agg["subagent_tools"], "tool", limit=15))
    L.append("\n### MCP servers\n")
    L.append(md_table(["server", "calls", "top tools"], [
        (srv, d["total"], ", ".join(f"{t} ({n})" for t, n in d["top_tools"].items()))
        for srv, d in agg["mcp_servers"].items()
    ]))
    L.append("\n### Skill invocations\n")
    L.append(counter_table(agg["skills"], "skill"))
    a = agg["agent"]
    L.append("\n### Agent dispatches\n")
    L.append(md_table(["metric", "value"], [
        ("Agent calls", a["dispatches"]),
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
    L.append("\n## Feedback signals (human messages)\n")
    L.append("Messages matching at least one marker per category:\n")
    L.append(counter_table(agg["feedback_messages"], "category", "messages"))
    L.append("\nPer marker (total matches):\n")
    L.append(counter_table(agg["feedback_markers"], "marker", "matches"))
    L.append("\n### Steering\n")
    L.append(md_table(["metric", "value"], [
        ("human turns arriving while assistant was mid tool run (heuristic)", agg["mid_run_steering"]),
        ("prompts with promptSource=queued (harness marker)", agg["queued_prompts"]),
        ("interrupts", agg["interrupts"]),
        ("share of human turns that were mid-run", f"{100 * agg['mid_run_steering'] / max(1, agg['user_turns']):.1f}%"),
    ]))
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
        {"type": "assistant", "timestamp": ts.format(1), "message": {"id": "m1", "content": [
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
    print("self-test ok")


SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|xox[a-z]-[A-Za-z0-9\-]{8,}|gh[pous]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}"
    r"|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}|Bearer\s+\S{16,}|\b\d{8,}:[A-Za-z0-9_\-]{30,}"
    r"|\b[0-9a-f]{32,}\b|[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}|[A-Za-z0-9_\-]{40,})"
)


def print_user_turns(projects_dir, sid_prefix, max_chars):
    """Stream one session's human turns to stdout with secret-shaped strings redacted.

    Used by the mining-session-practices skill for its bounded qualitative read:
    the agent reads a handful of sessions this way instead of opening JSONL
    files. Nothing is written to disk.
    """
    matches = []
    for pdir in os.scandir(projects_dir):
        if not pdir.is_dir():
            continue
        for entry in os.scandir(pdir.path):
            if entry.is_file() and entry.name.endswith(".jsonl") and entry.name.startswith(sid_prefix):
                matches.append(entry.path)
    if not matches:
        codex_dir = os.path.expanduser("~/.codex")
        for sub in ("sessions", "archived_sessions"):
            root = os.path.join(codex_dir, sub)
            for dirpath, _dirs, files in os.walk(root) if os.path.isdir(root) else []:
                for f in files:
                    if f.endswith(".jsonl") and sid_prefix in f:
                        matches.append(os.path.join(dirpath, f))
        if len(matches) == 1:
            return print_codex_user_turns(matches[0], max_chars)
    if len(matches) != 1:
        print(f"expected exactly one session matching {sid_prefix!r}, found {len(matches)}", file=sys.stderr)
        for m in matches[:10]:
            print("  " + os.path.basename(m)[:-6], file=sys.stderr)
        return 2
    n = 0
    with open(matches[0], encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") != "user" or ev.get("isSidechain"):
                continue
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            text = user_text(msg.get("content"))
            if text is None:
                continue
            origin = ev.get("origin") if isinstance(ev.get("origin"), dict) else {}
            stripped = text.lstrip()
            if ev.get("isMeta") or (origin and origin.get("kind") != "human"):
                continue
            if stripped.startswith(SKIP_PREFIXES) or stripped.startswith(INTERRUPT_PREFIX):
                continue
            n += 1
            red = " ".join(SECRET_RE.sub("[redacted]", text).split())
            tail = "..." if len(red) > max_chars else ""
            print(f"{n:03d} {str(ev.get('timestamp', ''))[:16]} | {red[:max_chars]}{tail}")
    print(f"# {n} human turns, redacted, stdout only", file=sys.stderr)
    return 0

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


def scan_codex_file(path, tz):
    sess = None
    seen = set()
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
            sess.touch(ts)
            sess.human_turn(text, ts, tz)
            continue
        if t == "response_item":
            if pt == "message" and pl.get("role") == "assistant":
                sess.assistant_turn(ts, pl.get("id") or str(ev.get("ordinal")), False)
            elif pt in ("function_call", "custom_tool_call"):
                sess.tool(pl.get("name"), ts)
        elif t == "event_msg":
            if pt == "agent_message":
                sess.assistant_turn(ts, str(ev.get("ordinal")), False)
            elif pt == "turn_aborted":
                sess.interrupts += 1
    return sess


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
    ("codex", "~/.codex/sessions", "parsed"),
    ("codex (archived)", "~/.codex/archived_sessions", "parsed"),
    ("opencode", "~/.local/share/opencode", "detected only; parser pending"),
    ("pi", "~/.pi/agent/sessions", "detected only"),
    ("goose", "~/.local/share/goose/sessions", "detected only"),
    ("gemini-cli", "~/.gemini/tmp", "detected only"),
    ("amp", "~/.local/share/amp", "detected only"),
    ("amp (alt)", "~/.amp", "detected only"),
    ("cursor", "~/Library/Application Support/Cursor/User/globalStorage", "parsed"),
    ("cline", "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev", "detected only"),
    ("copilot-cli", "~/.copilot", "detected only; holds hooks and skills, no sessions"),
    ("aider", "~/.aider", "detected only; chat history is per repo (.aider.chat.history.md), not parsed"),
    ("kiro", "~/.kiro", "detected only"),
    ("hermes", "~/.hermes", "detected only"),
    ("orca", "~/Library/Application Support/Orca", "metadata only; its sessions are Claude Code or Codex files"),
    ("conductor", "~/conductor", "workspaces only; its sessions are Claude Code files"),
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
        rows.append((name, path, files, f"{size / 1e6:.1f} MB", last, status))
    print(md_table(["harness", "path", "files", "size", "newest", "status"], rows) if rows else "no known agent stores found")


def print_codex_user_turns(path, max_chars):
    n = 0
    for ev in iter_codex_events(path):
        text = codex_human_text(ev)
        if text is None:
            continue
        n += 1
        red = " ".join(SECRET_RE.sub("[redacted]", text).split())
        tail = "..." if len(red) > max_chars else ""
        print(f"{n:03d} {str(ev.get('timestamp', ''))[:16]} | {red[:max_chars]}{tail}")
    print(f"# {n} human turns, redacted, stdout only", file=sys.stderr)
    return 0

CURSOR_USER_DIR = os.path.expanduser("~/Library/Application Support/Cursor/User")


def cursor_workspace_labels(db):
    labels = {}
    for wj in glob.glob(os.path.join(CURSOR_USER_DIR, "workspaceStorage", "*", "workspace.json")):
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


def scan_cursor(since_days, tz):
    """Cursor agent chats live in globalStorage/state.vscdb: composerHeaders (index) and
    cursorDiskKV rows composerData:<id> and bubbleId:<composer>:<bubble>. Bubble type 1 is the
    human, type 2 the assistant; a type 2 bubble with toolFormerData is one tool call. Subagent
    composers (isSubagent=1) are attributed to the parent as subagent tool calls."""
    db_path = os.path.join(CURSOR_USER_DIR, "globalStorage", "state.vscdb")
    if not os.path.isfile(db_path):
        return []
    cutoff_ms = (time.time() - since_days * 86400) * 1000 if since_days else None
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
        db.execute("select 1 from composerHeaders limit 1")
    except sqlite3.Error:
        return []
    labels = cursor_workspace_labels(db)
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
        r = db.execute("select value from cursorDiskKV where key=?", (f"composerData:{cid}",)).fetchone()
        if not r:
            continue
        try:
            cd = json.loads(r[0])
        except Exception:
            continue
        mname = (cd.get("modelConfig") or {}).get("modelName")
        if mname:
            sess.models[str(mname)[:40]] += 1
        for hdr in cd.get("fullConversationHeadersOnly") or []:
            b = db.execute("select value from cursorDiskKV where key=?", (f"bubbleId:{cid}:{hdr.get('bubbleId')}",)).fetchone()
            if not b:
                continue
            try:
                bub = json.loads(b[0])
            except Exception:
                continue
            ts = parse_ts(bub.get("createdAt"))
            if bub.get("type") == 1:
                text = bub.get("text") or ""
                if is_sub or not text.strip():
                    continue
                sess.touch(ts)
                sess.human_turn(text, ts, tz)
            elif bub.get("type") == 2:
                tf = bub.get("toolFormerData")
                if tf:
                    name = str(tf.get("name") or "(unnamed)")[:60]
                    if is_sub:
                        sess.sub_tool_calls[name] += 1
                    else:
                        sess.tool(name, ts)
                elif not is_sub:
                    sess.assistant_turn(ts, bub.get("requestId") or hdr.get("bubbleId") or "?", False)
    db.close()
    return [sessions[k] for k in order]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--since-days", type=int, default=None, help="only files modified in the last N days")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--exclude", action="append", default=[], help="skip files whose path contains this (repeatable)")
    ap.add_argument("--tz", default="Europe/Lisbon")
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--notes", default=None, help="markdown file appended verbatim to the report")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--discover", action="store_true", help="list known agent stores present on this machine and exit")
    ap.add_argument("--codex-dir", default=os.path.expanduser("~/.codex"))
    ap.add_argument("--no-codex", action="store_true", help="skip Codex threads")
    ap.add_argument("--no-cursor", action="store_true", help="skip Cursor agent chats")
    ap.add_argument("--user-turns", metavar="SESSION_ID", default=None,
                    help="print one session's human turns (redacted) to stdout and exit; id prefix allowed")
    ap.add_argument("--max-chars", type=int, default=700, help="truncate each printed turn (with --user-turns)")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if args.user_turns:
        sys.exit(print_user_turns(args.projects_dir, args.user_turns, args.max_chars))
    if args.discover:
        discover_stores()
        return
    tz = ZoneInfo(args.tz)
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
        for i, path in enumerate(codex_files, 1):
            s = scan_codex_file(path, tz)
            if s is not None:
                sessions.append(s)
            print(f"[codex {i}/{len(codex_files)}] {os.path.basename(path)[:40]} turns={s.user_turns if s else 0}", file=sys.stderr)
    cursor_sessions = []
    if not args.no_cursor:
        cursor_sessions = scan_cursor(args.since_days, tz)
        sessions.extend(cursor_sessions)
        print(f"[cursor] {len(cursor_sessions)} agent chats", file=sys.stderr)
    sessions = [s for s in sessions if s.start]
    sessions.sort(key=lambda s: s.start)
    rows = [s.row() for s in sessions]
    agg = aggregate(sessions, tz, args.weeks)
    scope = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "projects_dir": args.projects_dir,
        "session_files": len(found),
        "codex_files": len(codex_files),
        "cursor_sessions": len(cursor_sessions),
        "skipped_files": len(skipped),
        "skipped_reasons": dict(Counter(reason for _p, reason in skipped)),
        "since_days": args.since_days,
        "excludes": args.exclude,
        "first_start": rows[0]["start"] if rows else None,
        "last_end": max((r["end"] for r in rows if r["end"]), default=None),
        "scan_seconds": round(time.time() - t0, 1),
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "session_miner_output.json"), "w") as fh:
        json.dump({"scope": scope, "aggregates": agg, "sessions": rows}, fh, indent=1, default=str)
    report = render_report(agg, rows, scope, args.tz)
    if args.notes and os.path.isfile(args.notes):
        with open(args.notes) as fh:
            report += "\n" + fh.read()
    with open(os.path.join(args.out, "session_miner_report.md"), "w") as fh:
        fh.write(report)
    print(f"done: {len(rows)} sessions in {scope['scan_seconds']}s -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
