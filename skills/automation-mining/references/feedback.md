# Feedback file — what the skill's author needs to improve it

Offer this once, in one line, when the run ends: after the verdicts, or the
moment the owner stops early — an abandoned run is the most useful feedback
there is. If they say yes, ask the four questions below, write
`mining-feedback-{date}.md` next to the report, and tell them to read it
once and send it to whoever handed them the skill.

You fill everything the session already knows; the owner answers four
questions, once, on one screen. Never re-ask what they already said — the
verdicts and "what is not on the list" go in from step 8 as they said them,
minus what hard rule 5 forbids: a colleague's name becomes their role, a
link or pasted message text is dropped, and the cut is marked `[…]`. The
same applies to the free text under the four questions. The file carries
headlines and counts, never evidence: no links, no message text, no names
of the people who were mined. Hard rule 5 binds this file too.

## The four questions

Ask them together — with the host's structured-question tool when it has
one (in Claude Code, `AskUserQuestion`: four questions in one call, options
under each), otherwise as one message with lettered options. Free text
stays open on every question.

1. **Against what you expected going in, this run** — found things I didn't know · confirmed what I already knew · was mostly generic · got my work wrong
2. **Where did it lose you, if anywhere?** (any that apply) — the seed question: unclear, badly timed, or asked twice · the shape check: hard to read, too much, or the wrong patterns · the proposals: vague, not buildable, or misread · nowhere, it read fine
3. **Which one would you switch on for two weeks?** — the proposals that got "build it", by headline, up to three · none of them
4. **Would you run this again on another surface?** — yes, as is · yes, if something changed (what?) · no (why?)

Question 3 is dropped when nothing got "build it" or the run stopped before
proposals; the other three are asked either way. Question 1 is the
deck-level read the per-proposal verdicts cannot give; question 2 maps
straight onto a step of the skill; question 3 names the automation to check
on in two weeks; question 4 is the thesis.

## The file

```markdown
# Mining feedback — {date}

skill: automation-mining {version from SKILL.md} · host: {Claude Code | other} · model: {if known}
owner: {name or team, as they like} · lens: {owner of the surface | not the owner — whose answer seeded the run}
run: {finished with verdicts | stopped at step {N} — one line on why}

## Surfaces
- {surface, type} · {from → to} · {N units listed, M opened} · workers: {none | N on {model}} · {wall clock, if known}
- trail: {surface} — {followed | verify only | skipped | not connected, asked}   (one line per trail)

## Process — from the transcript, not from memory
- seed question: {asked once, before any read | skipped — why}
- shape check: {before deep work? one screen? what the steer changed}
- surfaces opened only after an ask: {yes | no — which}
- evidence spot-check: {N of N links resolve}
- read-only: {held | what was written, where}
- coverage stated: {yes | no}
- deviations: {each place you departed from SKILL.md, and why}
- friction: {an instruction read two ways, a limit hit, a worker that died, a tool quirk that cost a retry}
- cost: {tokens if the host shows them, else reads and minutes}

## Deck and verdicts — as the owner said them, rule 5 applied
- {headline} · {N in window} · {build it | real but not worth it | you misread this} — {their why, names and links out}
- not on the list: {their answer, names and links out} · {on a surface you read: yes/no; what the re-look found}

## Four answers
1. against expectations: {answer}
2. lost you at: {answer}
3. two weeks: {answer | not asked — nothing got "build it" | not asked — stopped before proposals}
4. run again: {answer}
```

Deviations and friction are the lines that change the skill: a step every
run skips is a step to delete; an instruction every run reads two ways is
one to rewrite. Report them plainly — the author needs the miss, not a
defence of it.
