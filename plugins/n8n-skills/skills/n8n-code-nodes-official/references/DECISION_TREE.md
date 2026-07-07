# Decision tree

The bar for using a Code node is high. This file walks through verifying that simpler alternatives (expression, Edit Fields arrow function) don't work.

## Stage 1: try an expression

For any single-field transform, ask: can this fit in `{{...}}`?

Expressions express:

- Property access (`$json.foo.bar`)
- Method chains (`$json.items.filter(...).map(...).join(...)`)
- Ternary conditionals
- Arithmetic and string interpolation
- Date math via Luxon
- Native JS methods on arrays/strings/objects/numbers

If it fits one line, even a long one, do it as an expression. Multi-line indented form is supported. See the `n8n-expressions-official` skill.

**Test:** can you describe it as "take A and produce B" without intermediate variables? If yes, expression.

```ts
// Expression: "take items, return joined names"
{{ $json.items.map(item => item.name).join(', ') }}

// Expression: "take created_at, return YYYY-MM-DD"
{{ DateTime.fromISO($json.created_at).toFormat('yyyy-MM-dd') }}

// Expression: "take items, return their total"
{{ $json.items.reduce((sum, item) => sum + item.price, 0) }}
```

## Stage 2: try Edit Fields with an arrow function

When the transform needs intermediate variables, multi-step logic, or doesn't fit one line, use Edit Fields with an inline arrow function.

Pattern: an immediately-invoked arrow function inside the expression.

```ts
{{ (() => {
    const items = $json.items
    const total = items.reduce((sum, item) => sum + item.price, 0)
    const tax = total * 0.08
    return `Total: $${(total + tax).toFixed(2)}`
})() }}
```

This buys you:

- Multiple statements
- Local variables
- Early returns
- Comments

What you give up vs. a Code node:

- No external libraries
- No `require`s
- No access to `$input.all()` (you have `$json` for the current item, not all items at once)

For more, see `ARROW_FUNCTIONS_IN_EDIT_FIELDS.md`.

**Test:** does the logic operate on a single input item (`$json`)? If yes, Edit Fields. If you need to combine items, see Stage 3.

## Stage 3: justify the Code node

Stages 1 and 2 are ruled out. Remaining valid reasons:

### Reason A: External libraries

JS Code supports a curated allowlist (lodash, crypto, luxon). If you genuinely need `lodash.groupBy` or one of the others, Code is necessary. No HTTP client is bundled, use the HTTP Request node for any outbound calls.

Counter-question: do you actually need lodash? Modern JS has `Array.prototype.reduce` and `Object.entries`.

### Reason B: Multi-source aggregation across the whole dataset

Most common valid case. When a node needs to:

- Read from **multiple upstream nodes simultaneously**.
- Compute statistics or transformations **across all items at once**.
- Apply multi-step logic with intermediate data structures.

Code, full stop. Don't split across many Edit Fields.

Splitting an analytics rollup into 10+ smaller nodes is harder to read, debug, and iterate than one 80-line Code node with clear sections.

But: ask if part can be a built-in (Aggregate, Summarize, Sort, Group). Check via `search_nodes`. If a built-in covers half, do that half there.

### Reason B-adjacent: Statistical operations across many items

Median, percentile, ratio-of-ratios, normalized scores: anything needing all items to compute an answer for any one. Single-item tools can't express this.

### Reason C: Crypto operations

HMAC signing, JWT verification, custom encryption. JS has `require('crypto')`. Python has `hashlib` and `hmac`.

Counter-question: is this for *auth*? See `n8n-credentials-and-security-official`. `httpCustomAuth` may handle it without code.

### Reason D: User has existing JS/Python they want to drop in

Worth pushing back on. n8n workflows are visual, and dropping a 200-line script defeats most of the value. Options:

- Refactor into multiple nodes.
- Run as a separate service called via HTTP Request.
- Decide this case justifies one Code node and document why in the description.

## When the user insists on a Code node

Their call. Build it, but:

- Comment in the Code node explaining why simpler tools weren't used.
- Keep small. 
- Run the workflow and verify outputs before publishing.

## Examples by category

### "Format a date"

- One format: expression (Luxon).
- Multiple formats: Edit Fields with arrow function.
- Code node: only if you're computing dates from non-trivial sources (e.g., parsing freeform user input with intent disambiguation).

### "Filter items by criteria"

- Simple: expression on the previous node's output, or use the IF node.
- Conditional with multiple criteria: Edit Fields arrow function.
- Code node: only if criteria depend on aggregate stats across all input items.

### "Build an email body"

- Static template with field substitution: expression in the email node's body field.
- Conditional sections: arrow function in the email body field.
- Code node: never. Building strings is the most over-Code'd pattern in n8n.

### "Transform API response into target shape"

- One-to-one field mapping: Edit Fields with expressions.
- Map/filter/reduce on arrays in the response: still expressions.
- Combining responses from multiple HTTP calls: Merge node + Edit Fields. Code node only if the merge logic is genuinely complex.

### "Validate input data"

- Use the IF node or built-in validation nodes (`schema validation` if available).
- Edit Fields with arrow function for "compute a `valid` boolean."
- Code node: rare, and usually a sign that validation should happen upstream of n8n.

## The honest answer

Code feels productive because writing JS is what you know. But the workflow gets read by someone (maybe future-you) who has to understand each node at a glance, modify one piece without breaking others, and debug from runtime errors.

Visual nodes with descriptive names beat a Code block on every one. 30 seconds saved now costs hours later.

When in doubt: not a Code node.
