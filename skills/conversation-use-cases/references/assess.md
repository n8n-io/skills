# Assess mode: problems across several people

Input: a folder holding one `conversation-use-cases-<date>.md` per person, as they shared them. Output: `assessment-<YYYY-MM-DD>.md` in the same folder. The main agent reads no report itself; it dispatches, collects, and writes the output from what the subagents return. People are called person A, B, C in the order the files sort; no names anywhere.

## Step 1: one subagent per report, in parallel

Brief, verbatim, with the file path filled in:

> Read only the file `<path>`. It is one person's report: counts from their agent history and, in section 8, their own words. Return, and nothing else, at most 40 lines:
> - `PROBLEMS`: every distinct problem the person has, one line each, in this form: `P<n>: <one-line statement> | evidence: <the section 2, 3, 4 or 6 numbers that support or contradict it, with denominators> | words: "<a short quote from section 8, or none>"`. Section 8 is the only text you may quote. Do not invent a problem the report does not show.
> - `ASKS`: the top five rows of section 3 as `category: N of D (P%)`.
> - `FRUSTRATION`: the section 2 count and share, the two preceding signals, and the one-line paraphrase as written.
> - `MOMENTS`: the moments present in section 6 with occurrences and sessions.
> - `CARDS`: the top five rows of section 7 as `card: gate, share`.
> - `GAPS`: anything the person wrote in section 8 that no row of sections 2 to 7 measures.
> Rules: quote only section 8; never copy other prose; no names, companies, projects, paths or URLs; write nothing to disk.

## Step 2: one subagent over all the returns

Brief, verbatim, with the step 1 returns pasted in, labelled person A, B, C:

> Below are per-person extracts from `<n>` reports. Return, and nothing else, the four tables of the output template filled in:
> 1. `Problem clusters`: group the `PROBLEMS` lines that describe the same problem across people. One row per cluster: cluster name (a problem, never a feature), people count, one supporting quote per person from their `words` field (verbatim, labelled person A, B, C), the evidence lines that support it, the evidence lines that contradict it, and the cards it points at from the list below, or `no card`. Order by people count, then by evidence.
> 2. `Disagreements`: places where two people's problems or numbers pull in opposite directions, one row each, with both sides.
> 3. `Uncovered`: clusters with `no card`, and every `GAPS` line that repeats across people. These are candidate use-cases; describe each as the problem only.
> 4. `Per person`: one line per person: their loudest problem in their own words and the one number that best backs it.
> Cards: <paste the `#` and `Use-case` columns of the Cards table in references/use-cases.md>.
> Rules: quote only the `words` fields; no names; write nothing to disk; no em dashes.

## Output template

```
# Assessment of <n> conversation-use-cases reports, <YYYY-MM-DD>

## 0. Inputs
| Person | Report date | Sessions | Human turns | Harnesses |

## 1. Problem clusters
| Cluster (the problem) | People | In their words | Supporting evidence | Contradicting evidence | Cards |

## 2. Disagreements
| Topic | One side | Other side |

## 3. Uncovered: candidate use-cases, as problems
| Problem | People | In their words | What the reports measure about it |

## 4. Per person
| Person | Loudest problem, in their words | Number behind it |
```

## Rules for the whole mode

- The main agent writes the output from the subagent returns only; it does not open the reports.
- Section 8 quotes are the only verbatim text. People are A, B, C. No other names, companies, projects, paths or URLs.
- Clusters are problems. A row that names a feature, a Block or a card as the cluster is rewritten as the problem it solves.
- No em dashes.
