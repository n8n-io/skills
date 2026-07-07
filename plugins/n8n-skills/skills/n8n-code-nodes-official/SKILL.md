---
name: n8n-code-nodes-official
description: Use when the user reaches for a Code node, mentions writing JavaScript or Python in n8n, or any custom logic comes up in workflow design. Triggers on "Code node", "Code", "JavaScript", "Python", "custom logic", "transform data", "$input", "$json transformation", "loop in code", "write a function", or any time the obvious answer seems to be "just put it in code."
---

# n8n Code Nodes

The Code node is powerful and often the wrong tool. The n8n equivalent of dropping into raw SQL when an ORM would do: real cases exist, but the moment a Code node handles logic an expression could, the workflow is harder to read, debug, and maintain. There's also a real perf gap: Code runs in a sandboxed JS runtime, expressions and Edit Fields run in-process, and the per-invocation overhead can be hundreds of times higher in Code (anecdotally ~2ms vs ~600ms for equivalent logic). For hot paths and large item counts, that compounds.

## Strong defaults

1. **Code node is a last resort.** Decision order: expression (`{{...}}`) → arrow function inside Edit Fields → Code node. The first two paths cover most "transform this data" tasks. Code earns its place for multi-source aggregation, external libraries, and a few specific patterns documented below.

2. **Default to JavaScript.** Write JS unless the user explicitly asked for Python ("use Python here," "I'm a Python shop," pasted Python code). Everywhere else in n8n (expressions, Edit Fields) is JS, JS has a curated library allowlist (`lodash`, `crypto`, `luxon`).

## Decision tree

```
Need custom logic?
├── Is it a transformation of one or two fields?
│   └── Expression: {{ $json.foo.toUpperCase() }} or {{ $json.items.map(item => item.name).join(', ') }}
│       Most "just transform this" cases land here.
│
├── Is it multi-line, but pure data shaping (map, filter, reduce, conditional)?
│   └── Edit Fields with arrow function expression. See references/ARROW_FUNCTIONS_IN_EDIT_FIELDS.md
│
├── Does it need full statements, multiple data sources, or external libs?
│   ├── Are you SURE the above two don't work?
│   │   └── Re-read the parent. The bar is high.
│   └── Yes, genuinely needs it
│       └── Code node. See references/JAVASCRIPT_PATTERNS.md
│
└── Is it actually two separate transformations stitched together?
    └── Use two nodes (Edit Fields → Edit Fields, or Edit Fields → IF). Composability beats one big Code block.
```

For the full decision logic with examples for each branch, see `references/DECISION_TREE.md`.

## What expressions can do that people forget

Common reaches-for-Code-node that should be expressions:

```ts
// ❌ Code node
return { name: $input.first().json.name.toUpperCase() }

// ✅ Expression in Edit Fields, "name" field
{{ $json.name.toUpperCase() }}
```

```ts
// ❌ Code node
const items = $input.first().json.items
return { tags: items.map(item => item.tag).filter(tag => tag).join(', ') }

// ✅ Expression
{{ $json.items.map(item => item.tag).filter(tag => tag).join(', ') }}
```

```ts
// ❌ Code node
const date = new Date($input.first().json.created_at)
return { formatted: date.toISOString().slice(0, 10) }

// ✅ Expression with n8n's date extension
{{ $json.created_at.toDateTime().format('yyyy-MM-dd') }}
```

For more on what expressions can express, see the `n8n-expressions-official` skill.

## What arrow-functions-in-Edit-Fields can do

Edit Fields assigns field values via expression. Inline arrow functions get you most multi-line logic without the Code node:

```ts
// In Edit Fields, "summary" field:
{{ (() => {
    const items = $json.items
    const total = items.reduce((sum, item) => sum + item.price, 0)
    const tax = total * 0.08
    return `Total: $${(total + tax).toFixed(2)}`
})() }}
```

Right tool for "logic slightly too gnarly for a one-liner." See `references/ARROW_FUNCTIONS_IN_EDIT_FIELDS.md` for patterns and formatting.

## When the Code node IS the right answer

Real uses exist. Bar is high, not "never." The cases below are **legitimate**. Build with code without apologizing.

### Multi-source aggregation across the whole dataset

When a node needs to:

- Read from **multiple upstream nodes simultaneously** (e.g., `$('Source A').all()`, `$('Source B').all()`, `$('Source C').first().json`).
- Compute statistics or transformations **across all items at once** (not per-item).
- Apply multi-step logic with intermediate data structures (lookup maps, accumulators, ratios).

Most common valid case. Examples:

- Analytics rollups: per-group averages, percentile scoring, normalization across categories.
- Building lookup tables from one source and joining against rows from another.
- Computing offsets/ratios across two reference datasets, then applying to a third.

```ts
// Real-world shape: aggregate test results from one source,
// model metadata from another, category mapping from a third,
// and produce per-model-per-category averages.

const testResults = $('Get Test Results').all().map(item => item.json)
const models = $('Get Models').all().map(item => item.json)
const categoryMap = $('Get Category Map').first().json.testCategoryMap

const categoryByTestId = Object.fromEntries(
    categoryMap.map(mapping => [mapping.testId, mapping.category])
)

const result = models.map(model => {
    const modelTests = testResults.filter(test => test.modelId === model.id)
    const stats = modelTests.reduce((acc, test) => {
        const cat = categoryByTestId[test.testId]
        if (!cat) return acc
        acc[cat] ??= { scored: 0, available: 0, count: 0 }
        acc[cat].scored += test.pointsScored ?? 0
        acc[cat].available += test.pointsAvailable ?? 0
        acc[cat].count += 1
        return acc
    }, {})

    const averages = Object.fromEntries(
        Object.entries(stats).map(([category, stat]) => [
            category,
            { avg: stat.available > 0 ? stat.scored / stat.available : 0, n: stat.count }
        ])
    )

    return { modelId: model.id, modelName: model.modelName, ...averages }
})

return result.map(json => ({ json }))
```

Technically expressions can reach across items via `$('Node Name').all()` and reduce inline, but for anything with this much shape (joins, group-bys, nested aggregation) the result is a one-line megaexpression that's hard to read and impossible to debug. Use Code.

### External libraries

JS Code can `require` from a curated allowlist (lodash, etc.), but expressions can't. 

**Always check for a native node first.** n8n has more native nodes than people realize. Dropping into Code for something with a native node is a recurring mistake. The next two subsections cover the specific traps.

### Cryptographic operations: use the Crypto node, not Code

HMAC, signing, hashing, encryption: **n8n has a native Crypto node (`n8n-nodes-base.crypto`).** Use it. It handles SHA256, MD5, HMAC, encrypt/decrypt, and random generation, all without writing JavaScript.

```ts
// WRONG (recurring AI slip):
const crypto = require('crypto')
const hash = crypto.createHash('sha256').update(buf).digest('hex').slice(0, 12)

// RIGHT: configure the Crypto node with operation: 'hash', type: 'SHA256'
//   then read $('Hash').item.json.<output> downstream.
```

The Code-with-`require('crypto')` pattern is one of the most common false positives for "this needs a Code node." It doesn't. The Crypto node covers it.

#### Hashing binary, not strings

Don't reach for Code just because you need to hash *binary* (a PDF, an image, a file buffer). The Crypto node has a `binaryPropertyName` parameter. Point it at the binary slot key and it hashes the buffer directly. You don't need `this.helpers.getBinaryDataBuffer(...)` in user code.

```ts
// WRONG (recurring AI slip with binary):
const crypto = require('crypto')
const buf = await this.helpers.getBinaryDataBuffer($itemIndex, 'data')
const hash = crypto.createHash('sha256').update(buf).digest('hex')

// RIGHT: Crypto node configured to hash binaryPropertyName='data', SHA256.
//   Then $('Crypto').item.json.<output> has the hash; chain a Set node for any field shaping.
```

The remaining valid Code-for-crypto case: a non-standard signing scheme that the Crypto node doesn't expose (e.g., a custom AWS-style signature), AND `httpCustomAuth` credential doesn't fit either. Rare. Justify explicitly.

### XML / SOAP / RSS parsing: use the XML node, not Code

**n8n has a native XML node (`n8n-nodes-base.xml`)** with parse and stringify operations. It already converts XML to JSON. Once it has, the result is plain JSON and Edit Fields with arrow function expressions handles all the field extraction, array normalization (`Array.isArray(...) ? ... : ...`), and link-finding (`.find()`) you'd reach for Code to do.

```ts
// WRONG (recurring AI slip):
// XML node already parsed → another Code node to extract a few fields:
const entry = $('Parse XML').item.json.feed.entry
const firstEntry = Array.isArray(entry) ? entry[0] : entry
return { json: { title: firstEntry.title, url: firstEntry.link.find(link => link.type === 'pdf').href } }

// RIGHT: Edit Fields with arrow function expressions:
//   title:  ={{ (() => { const entry = $('Parse XML').item.json.feed.entry; return Array.isArray(entry) ? entry[0].title : entry.title; })() }}
//   pdfUrl: ={{ $('Parse XML').item.json.feed.entry.link.find(link => link.type === 'pdf')?.href }}
```

If the field-extraction logic is genuinely too gnarly for inline expressions even with multi-line arrow functions, the next stop is Edit Fields with a single multi-line arrow function, NOT a Code node. See `references/ARROW_FUNCTIONS_IN_EDIT_FIELDS.md`.

### What these have in common

Valid cases are about **scope**: whole-dataset, multiple sources, or stateful constructs single-item tools can't reach. Invalid cases: Code doing what an expression could, OR what a native node already does.

Quick tests:

- **"Could I describe this Code node's job as 'take this one item and...'?"** If yes, wrong tool.
- **"Is there a native node for this?"** Search via `search_nodes` first. Crypto, XML, JSON parsing, date math (Luxon), HTTP calls, file I/O, regex matching: all have native nodes or expression-level support.

## JavaScript Code node specifics

Two modes:

- **Run Once for All Items (default, use this):** runs once with `$input.all()`. If you need per-item logic, just `for (const item of $input.all())` inside. This is the standard shape and almost always what you want.
- **Run Once for Each Item:** runs once per item with `$input.first()` (or `$input.item`). 

Common shape:

```ts
// Run Once for All Items
const items = $input.all()
const totals = items.map(item => ({
  ...item.json,
  total: item.json.qty * item.json.price,
}))
return totals.map(json => ({ json }))
```

The return must be an array of `{ json: ... }` objects (or `{ json: ..., binary: ... }`), not raw JSON.

For binary handling, error patterns, and Code-node-only bugs, see `references/JAVASCRIPT_PATTERNS.md`.


## Reference files

| File | Read when |
|---|---|
| `references/DECISION_TREE.md` | You're tempted to use a Code node and want to verify the simpler paths really don't work |
| `references/ARROW_FUNCTIONS_IN_EDIT_FIELDS.md` | The transformation is multi-line but pure data shaping |
| `references/JAVASCRIPT_PATTERNS.md` | Code node is genuinely needed and JS is the language |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Code node doing `return { x: $input.first().json.x.toUpperCase() }` | Whole node for one expression | Replace with an Edit Fields expression |
| Code node building HTML strings for an email body | The Email node's body field accepts expressions | Inline the expression into the email node |
| Code node using `new Date()` for date formatting | Loses to Luxon's clarity | Use Luxon in expression. See `n8n-expressions-official` |
| Set node + Code node combo (Set builds inputs, Code transforms) | Two nodes for what should be one Edit Fields | Collapse into one Edit Fields with arrow function |
| Pasting credentials/tokens into Code node text | Same leak as text fields | Use credentials, not Code node |

