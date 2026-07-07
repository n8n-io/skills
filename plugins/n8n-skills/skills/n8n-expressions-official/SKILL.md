---
name: n8n-expressions-official
description: Use when writing or reviewing n8n expressions (`{{...}}` syntax), `$json` / `$node` references, Luxon date code, or expression errors. Triggers on `{{}}`, `$json`, `$node`, `$input`, `DateTime`, `Luxon`, "expression error", "evaluating", "format date", "transform field", or any node-parameter assignment.
---

# n8n Expressions

n8n's expression language is JavaScript embedded in `{{...}}` blocks. They run synchronously, on a single item at a time (`$json`), with access to upstream nodes (`$('Name')`), Luxon for dates, and most of native JS.

## Non-negotiable

**Reference data by node name, not `$json`.** Use `$('Node Name').item.json.field` (or `.first().json.field`). `$json` works but breaks when any node clears item context (Aggregate, Code with Run for All, branching merges) or a refactor adds an intermediate. Failures are silent, and downstream gets the wrong data with no error. Node-name references are stable.

## Strong defaults

- **No Set nodes whose only purpose is to feed a single downstream field.** Inline the expression at the consumer. Set earns its place when 2+ consumers read the same derived value, the derivation is non-trivial, or the Set is a sub-workflow's final return-shaper. See "The Set-node antipattern" below.
- **Luxon for dates, not the DateTime node.** Date math, formatting, and parsing all work in expressions: `{{ DateTime.now().minus({ days: 7 }).toISO() }}`. The DateTime node is more visible on the canvas for beginner human users, but avoid it unless the user specifically asks for it.
- **Expressions over extra nodes generally.** Build the email body in the email node's body field, and compute the URL in the HTTP Request's URL field. Reach for an extra node when the transform is reused or the *primary purpose* of a section.
- **Multi-line expressions are indented and commented.** When an expression spans more than one line, format it like real code. Most n8n users are not coders, so explain the code with concise inline comments

## Why reference by node name (`$('Name').item.json.x`) over `$json.x`

`$json` means "the current item flowing into this node." Fine when the node is directly downstream of one source and nothing has cleared the item context (some nodes do: Aggregate, Code with `Run for All`, branching merges).

It breaks when:

- You insert a node between source and consumer (the consumer was reading `$json.x` from a node 3 steps back, and now the new intermediate node is what `$json` refers to).
- A node clears the context (Aggregate, certain merges, Code nodes that don't preserve shape).
- Branches converge via Merge. `$json` is whichever branch fired last, not deterministic.

`$('Get User').item.json.id` is unambiguous. Always the named node's first-item JSON, regardless of what's between.

**The exception that makes the rule:**

When branches converge and you need a stable reference point, **insert a NoOp node** at the convergence. Name it descriptively (e.g., `Combine Inputs`). Downstream nodes reference it by name.

```
Branch A ──┐
           ├─→ [NoOp: Combine Inputs] ──→ Downstream nodes use $('Combine Inputs').item.json.x
Branch B ──┘
```

NoOp survives refactors: inserting a transform between Combine Inputs and the consumer doesn't break the `$('Combine Inputs')` reference.

This pattern is **required** when downstream nodes need data from a node whose context gets cleared by an intermediate operation.

**If the branches produce different shapes, use a Set node instead of NoOp.** NoOp passes through whatever shape arrived, so downstream still has to know which branch fired. A Set node normalizes both branches into one shape, and downstream reads one set of fields:

```ts
// Set node: "Normalize Inputs"
name: `={{ $('Lookup by Email').item.json.name || $('Lookup by ID').item.json.full_name }}`
email: `={{ $('Lookup by Email').item.json.email || $('Lookup by ID').item.json.contact_email }}`
```

Downstream nodes reference `$('Normalize Inputs').item.json.name` regardless of which branch produced it.

## The Set-node antipattern 

The pattern AI agents often produce:

```
Webhook → Set: { customer_id: $json.body.customer_id, amount: $json.body.amount }
       → Postgres: WHERE id = {{ $json.customer_id }}
       → Email: Total is {{ $json.amount }}
```

The Set node does nothing useful. Each downstream node could read from the webhook directly:

```
Webhook → Postgres: WHERE id = {{ $('Webhook').item.json.body.customer_id }}
       → Email: Total is {{ $('Webhook').item.json.body.amount }}
```

The Set node only earns its place if:

- The same derived value is used by **multiple downstream consumers** (derivation non-trivial).
- The derivation is logic-heavy and a name aids readability.
- Multiple branches need the same shape, and a shared upstream reference is cleaner.
- **It's the final node of a sub-workflow, shaping the return contract.** Explicit exception: the "single consumer" is every caller, so the Set is the API boundary. Optional but encouraged for sub-workflows, and sometimes required when the prior node carries noise fields. See `n8n-subworkflows-official`.
- **You need to drop fields from the item by setting `Include Other Fields: false`.** Set is the cleanest way to whitelist an output shape. This is the underlying mechanism behind the sub-workflow return-shaper bullet above (preventing internal scratch fields from leaking to callers), but it applies anywhere you need a clean shape downstream.
- **You need to rename fields.** A Set keeps the rename visible in one place rather than spread across every consumer expression.

For "extract a field from the request body and use it once," **no** Set node. The expression goes in the consuming field.

For "extract once for many downstream uses," a Set node *is* legitimate. If only one consumer uses it, the Set is debt (except the return-shaper case above).

### Quick test for whether a Set node is needed

How many downstream nodes reference each field?

- **0 or 1** → delete, inline the expression.
- **2+** → may earn its place, especially if non-trivial.

Multiple consecutive Set nodes are almost certainly over-extraction. Collapse.

## What expressions can do

### Single-field transformation

```ts
{{ $json.name.toUpperCase() }}
{{ $json.email.toLowerCase().trim() }}
{{ $json.items.length }}
{{ $json.user.first_name + ' ' + $json.user.last_name }}
{{ `(${$json.user.phone.slice(0, 3)}) ${$json.user.phone.slice(3, 6)}-${$json.user.phone.slice(6, 10)}` }}
```

### Method chains: `.map()`, `.filter()`, `.find()`, `.reduce()`

Array methods are some of the most useful expression tools. They replace dozens of nodes.

```ts
{{ $json.tags.filter(tag => tag.active).map(tag => tag.name).join(', ') }}
{{ Object.values($json.scores).reduce((sum, score) => sum + score, 0) }}

// Find one matching item from another node's output
{{ $('Get Models').all().find(model => model.json.id === $json.modelId).json.modelName }}

// Filter array, then check shape
{{
  $('Get User\'s Entries').all()
    .map(item => item.json)
    .filter(entry => entry.prize_eligible === 'eligible')
    .length > 0
}}
```

#### Always indent multi-step chains and add comments

When a chain has 2+ method calls or non-obvious filter logic, format it across lines and comment. Readers may not be the author, so comments make intent legible to non-technical readers too.

```ts
{{
  // Find all entries that are still processing AFTER 1 hour
  // (used to allow re-submission since something likely went wrong)
  $('Get User\'s Entries').all()
    .map(item => item.json)
    .filter(entry =>
      entry.prize_eligible === 'processing' &&
      $now.diffTo(entry.created_at, 'minutes') > 60
    )
    .length > 0
}}
```

This kind of logic is common in routing nodes (Switch, IF). Un-commented, it's unreadable for most users.

#### `.all().map()` triggers an "execute once" question

When you use `$('Source Node').all().map(...)` (or `.filter()`, `.reduce()`) to process the entire dataset, the **expression itself iterates**. If the node has the default per-item execution mode, it runs once *per input item*, but each run does the full `.all()` aggregation: wasted work, and possibly wrong.

**Set the node to execute once when:**

- The expression uses `.all().map()` / `.all().filter()` / `.all().reduce()`.
- Output should be a single aggregated result, not per-item.

This is `executeOnce: true` on the node. Most nodes have it.

```ts
const aggregateNode = node({
    type: 'n8n-nodes-base.set',
    config: {
        executeOnce: true,            // important when using .all() in expressions
        parameters: {
            assignments: {
                assignments: [
                    {
                        name: 'totalEligible',
                        value: `={{
                            $('Get Entries').all()
                                .map(item => item.json)
                                .filter(entry => entry.eligible)
                                .length
                        }}`,
                        type: 'number',
                    },
                ],
            },
        },
    },
})
```

Forgetting `executeOnce` often still works but does N times the work for N items. Worse, if downstream expects one item, you get N.

**Counter-case: `.all()` as a per-item lookup, NOT aggregation.** When the `.all()` reads a *different* node and gets filtered by the current item's identity, you want per-item execution. Each iteration produces a different result, so it's real work, not wasted.

```ts
// Workflow: Get Tags (200 items) → Search Posts (10 items) → this Set Fields node.
// Each post carries a `tag_ids` array. Set Fields runs per-item (10 times)
// and resolves each post's tag_ids into the full tag objects.
tags: ={{
  $('Get Tags').all()
    .filter(tag => $('Search Posts').item.json.tag_ids.includes(tag.json.id))
}}
```

Setting `executeOnce: true` here would collapse the 10 outputs to 1.

The shape distinguishing the two:

- `$source.all()` *alone* (aggregating across the dataset) → `executeOnce: true`.
- `$source.all().filter(... matches $other.item.json.x)` (looking up by the current item) → leave `executeOnce` off.

**Quick test:** does the expression use `.all()` *without* combining it with another node's `.item`? If yes, the node should probably be `executeOnce: true`.

For the broader picture on iteration and explicit looping, see the `n8n-loops-official` skill.

### Conditionals

```ts
{{ $json.status === 'active' ? 'Active' : 'Inactive' }}
{{ $json.amount >= 100 ? 'Large' : ($json.amount >= 10 ? 'Medium' : 'Small') }}
```

### Date math (Luxon)

```ts
{{ DateTime.now().toISO() }}
{{ DateTime.fromISO($json.created_at).toFormat('yyyy-MM-dd') }}
{{ DateTime.now().minus({ days: 7 }).startOf('day').toISO() }}
{{ DateTime.fromISO($json.due).diffNow('days').days }}    // days from now (negative if past)
```

### Cross-node references (preferred over `$json`)

```ts
{{ $('Webhook Trigger').item.json.body.customer_id }}
{{ $('Lookup customer').item.json.email }}
{{ $('Combine Inputs').item.json.coupon_code }}    // NoOp convergence point
```

`.item` and `.first()` are mostly equivalent for single-item nodes, so pick one. `.first()` is more explicit, `.item` is shorter.

### Multi-line logic with an IIFE arrow function

When logic is too gnarly for one line but operates on a single item, wrap it in an immediately-invoked arrow function:

```ts
{{ (() => {
    // Compute total including tax
    const items = $json.line_items
    const subtotal = items.reduce((sum, item) => sum + item.price * item.qty, 0)
    const tax = subtotal * 0.08
    return (subtotal + tax).toFixed(2)
})() }}
```

Inside, you get the full expression scope (`$json`, `$('Node Name')`, `$now`, Luxon) plus the JS you'd write in any function: `const`/`let`, `if`/`switch`, `try`/`catch`, regex.

**Arguments don't work.** Expressions have no caller to pass them, so `(text) => text.replace(...)` has nothing to invoke it with. Reference values from the outer scope directly. The function still needs the IIFE wrapping (`(...)()`) to actually execute.

```ts
{{ (() => $json.text.replace(/\b(?:foo|bar)\b/gi, 'baz'))() }}
```

The outer `(` and trailing `)()` are mandatory: the first pair brackets the function expression, the trailing `()` invokes it. Drop either and n8n errors and refuses to run the workflow.

**Why this over a Code node?** The Code node runs in a sandboxed VM: roughly 500-1000ms worst case. The expression IIFE runs in the same context as the surrounding expression: 1-10ms consistently. For pure single-item shaping, that's a 100x gap with no functional difference. This is a common poweruser method.

A Code node still earns its place for multi-item aggregation (`$input.all()`), external libraries, or async work. See `n8n-code-nodes-official` for the decision tree, and `n8n-code-nodes-official` `ARROW_FUNCTIONS_IN_EDIT_FIELDS.md` for longer examples and formatting rules.

### Native JS available

`String`, `Array`, `Number`, `Object`, `Map`, `Set`, `JSON.parse`, `JSON.stringify`, `Math`, regular expressions, `Date` (but only use Luxon).

## Useful idioms

### Default value when a field might be missing

```ts
{{ $json.id || "fallback-id-here" }}
```

Or with optional chaining:

```ts
{{ $json.user?.profile?.id ?? "anonymous" }}
```

Especially useful for filter values feeding queries: pass a default that matches no rows rather than letting the query fail with `undefined`.

### Embedding JSON in a text field: which serializer

Two serializers, two contexts:

- **`.toJsonString()`** for compact JSON where formatting doesn't matter. Canonical case: **AI prompts**. Smaller, easier on tokens, easier to scan in a prompt template.
  ```ts
  {{ $('Get Data').item.json.toJsonString() }}
  ```
- **`JSON.stringify(value, null, 2)`** for pretty-printed JSON where formatting matters. Canonical case: **email bodies, Slack messages, debug output**, anywhere a human reads the result.
  ```ts
  {{ JSON.stringify($('Source Node').item.json, null, 2) }}
  ```

Pick deliberately. Pretty-printing inside an LLM prompt wastes tokens and clutters the model's context. Compact JSON in an email is unreadable.

### `JSON.stringify` and `JSON.parse`: where they belong

`JSON.stringify` and `JSON.parse` are common in expressions. Both are fine. The key discipline: **stringify and parse are storage-layer operations, not interface-layer operations.**

- **Stringify when you're writing into a storage column that doesn't natively hold the type.** The canonical case: a Data Tables `_object`-postfixed string column holding what's actually an array or object. See `n8n-data-tables-official`.
- **Parse when you're reading back out of that storage column.** Inside the workflow that owns the storage.
- **Don't propagate the stringified shape across boundaries.** Sub-workflow returns, webhook responses, agent tool results, downstream consumers: all of those should receive the natural shape (arrays as arrays, objects as objects), not a stringified shell that the caller has to remember to `JSON.parse`.

The classic slip: a sub-workflow has a "fresh" path (data just produced by an LLM, already an array) and a "cached" path (data just read from a `_object` column, still a string). The wrong instinct is to stringify the fresh path "to match" the cached one. The right instinct is to parse the cached path so both branches produce the same natural shape on the way out.

Storage representation belongs inside the workflow that owns the storage. Outside that boundary, talk in natural shapes. `n8n-subworkflows-official` SKILL.md "Return natural shapes, not storage shapes" covers this from the sub-workflow side, and `n8n-data-tables-official` covers it from the storage side.

### Returning the right type: when to wrap in `={{ ... }}`

Some node fields will treat your value as a string literal unless you tell n8n to evaluate it as an expression. Wrapping in `={{ ... }}` (the `=` prefix turns the field into expression mode) returns the actual type the inner code produces:

```ts
// String literal (default behavior)
foo: 'plain string'

// Number
foo: '={{ 100 }}'

// Boolean
foo: '={{ true }}'

// Object (the `={{ ... }}` is what makes the receiver see an object, not a string)
foo: '={{ { "valid": true, "items": [] } }}'

// Array
foo: '={{ ["a", "b", "c"] }}'

// Reference to another node's value (preserves whatever type that value already is)
foo: '={{ $("Source Node").item.json.payload }}'
```

When the type matters: object/array fields on Set / Edit Fields (with the column's `Type` set to Object or Array), JSON body parameters on HTTP Request, structured inputs to a sub-workflow's typed `workflowInputs.values[type]`, agent tool parameters, anywhere the receiving node validates the type. Without the `={{ ... }}` wrapper, you'd be passing a string and the receiver either coerces or errors.

**Reference by node name, not `$json`**, per non-negotiable #1 above:

```ts
// WRONG
foo: '={{ $json.payload }}'

// RIGHT
foo: '={{ $("Source Node").item.json.payload }}'
```

The exception: if `$json` is genuinely the right thing (no intermediate transforms, no convergence) and the field is a per-item slot on a node that's directly downstream of one source. Even then, named references are more refactor-safe.

### Multi-line expression with explanatory comment

```ts
{{
  // Default to avoid query errors when user_id is missing.
  // The fallback UUID is a known-empty row.
  $json.id || "305f7106-6988-4651-b26a-18979641b7b5"
}}
```

**Encouraged** when logic is non-obvious. The comment will be there for the next reader.

## What expressions CAN'T do

- Use external libraries (no `require`).
- Async / await.

`$json` itself is the current item only, but expressions *can* reach across items via `$input.all()`, `$input.all()[3]`, `$('Source Node').all()`, etc. See "Method chains" above.

For those, see `n8n-code-nodes-official`.

## Decision: expression, Edit Fields, or Code node?

Per `n8n-code-nodes-official`'s decision tree:

```
1. Single-field transform → expression in the field
2. Multi-step pure logic on one item → arrow function in Edit Fields
3. Multi-source aggregation, libraries, or stateful → Code node
```

Expression is the default. Reach past it only when input or scope demands it.

## The "extra node" smell

Common reaches-for-extra-nodes that should stay in expressions:

| Adding this node | Better as |
|---|---|
| DateTime node to format a date | `DateTime.fromISO(...).toFormat(...)` in the consumer's expression |
| Set node to build an email body | Inline the expression in the email node's body field |
| Set node to compute a derived field used once | Inline at the consumer |
| Two nodes (Set + IF) to compute then test | One IF with the computation in its condition expression |
| Code node to call `.toUpperCase()` | Just the expression |

Adding nodes for transforms means more visual clutter, slower workflows, harder reading.

When extra nodes ARE right:

- The transform is *reused* across multiple downstream consumers.
- The transform is heavy (Code node territory).
- The transform is the *primary purpose* of a section (a clear "compute X" step).

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Set node that exists to extract one field from a webhook body for one downstream consumer | Extra node for what should be inlined, fragile to refactor | Delete the Set node, reference `$('Webhook').item.json.body.x` directly in the consumer |
| Multiple consecutive Set nodes each defining one field | Workflow padding | Collapse. Most aren't needed, and for the ones that are, group into one Set node |
| Using `$json.x` deep in a workflow with multiple branches and intermediate transforms | Reference breaks when an intermediate is added or context is cleared | Use `$('Source Node').item.json.x`. Add a NoOp convergence point if branches merge. |
| Adding a DateTime node to format a timestamp | Extra node for what's a 1-line Luxon expression | `{{ DateTime.fromISO($('Source').item.json.x).toFormat('yyyy-MM-dd') }}` |
| Set node to build email HTML, then read it in the Email node | Two nodes for what's one expression | Build the HTML directly in the email node's body field |
| `new Date($json.created_at)` instead of Luxon | Loses formatting/manipulation features | `DateTime.fromISO($('Source').item.json.created_at)` |
| One-line expression that's actually 200 chars | Unreadable | Multi-line with arrow function, indented, with comments |
| `$json.foo.bar.baz` without checking `$json.foo` exists | Crashes on missing intermediate | Use `?.` chain: `$('Source').item.json.foo?.bar?.baz` |
| Hardcoding values in expressions that should be config | Magic strings | Use `$vars.X` (n8n Variables, paid plans) or a Data Table |
| Branches converge with `$json` references downstream | Whichever branch fired last wins, non-deterministic | Insert a NoOp ("Combine Inputs") at the merge, reference by name |
| Using `$env.X` in any expression | Doesn't work; throws at runtime | For config use `$vars.X` (paid plans) or a Data Table. For secrets use the credential system |