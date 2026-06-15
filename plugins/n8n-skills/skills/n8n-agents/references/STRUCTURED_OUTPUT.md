# Structured output

Non-negotiable: parse and retry on failure

## The pattern

```ts
const structuredParser = outputParser({
    type: '@n8n/n8n-nodes-langchain.outputParserStructured',
    config: {
        parameters: {
            schemaType: 'manual',
            inputSchema: JSON.stringify({
                type: 'object',
                properties: {
                    score: { type: 'integer', minimum: 1, maximum: 5 },
                    reason: { type: 'string' },
                },
                required: ['score', 'reason'],
            }),
            autoFix: true,
            customizeRetryPrompt: true,
            prompt: '...retry instructions...',
        },
        subnodes: {
            languageModel: fixerModel,
        },
    },
})

const aiAgent = node({
    type: '@n8n/n8n-nodes-langchain.agent',
    config: {
        parameters: {
            options: {
                systemMessage: '...you must respond in JSON matching {"score":...,"reason":...}...',
            },
        },
        subnodes: {
            model: mainModel,
            outputParser: structuredParser,
        },
    },
})
```

## Why a schema, not an example

`schemaType: 'manual'` with a real JSON Schema is the default. `jsonSchemaExample` looks easier, but an example can't express:

- **Required vs optional fields.** An example is one snapshot, the parser can't tell which keys are mandatory.
- **Enums.** `"category": "compliance"` doesn't constrain the model to `compliance | history | risk`. It'll invent new categories.
- **Numeric ranges.** `"score": 3` doesn't say `1-5`. The model will return `7` or `0.85` and pass the parser.
- **Array constraints.** Min items, max items, item type uniformity.
- **String formats.** Email, UUID, ISO date, regex patterns.

A schema gives the model clearer rules and gives the parser real validation:

```ts
inputSchema: JSON.stringify({
    type: 'object',
    properties: {
        decision: { type: 'string', enum: ['approve', 'reject', 'escalate'] },
        confidence: { type: 'number', minimum: 0, maximum: 1 },
        reasons: {
            type: 'array',
            items: {
                type: 'object',
                properties: {
                    category: { type: 'string', enum: ['compliance', 'history', 'risk'] },
                    weight: { type: 'number', minimum: 0, maximum: 1 },
                    note: { type: 'string' },
                },
                required: ['category', 'weight'],
            },
        },
        follow_up_required: { type: 'boolean' },
    },
    required: ['decision', 'confidence', 'reasons', 'follow_up_required'],
})
```

Reach for `schemaType: 'fromJson'` with `jsonSchemaExample` only for one-off shapes you're certain will never grow constraints. Once a field needs to be optional, enum-ed, or range-bounded, you're rewriting the parser anyway, so start with the schema.

## `autoFix: true` and the fixer model

The model can produce almost-but-not-quite-valid JSON: trailing comma, missing field, wrong type. Without `autoFix`, the workflow halts. With it, the parser sends the bad output to a model with a "fix this" prompt, retries, and continues.

```ts
{
    autoFix: true,
    customizeRetryPrompt: true,
    prompt: `Instructions:
--------------
{instructions}
--------------
Completion:
--------------
{completion}
--------------

Above, the Completion did not satisfy the constraints given in the Instructions.
Error:
--------------
{error}
--------------

Please try again. Please only respond with an answer that satisfies the constraints laid out in the Instructions.
This is a structured output parser tool in n8n. Ensure the output format is correct to pass the parsing.
DO NOT wrap the output in a markdown code block.`,
}
```

Placeholders `{instructions}`, `{completion}`, `{error}` are filled at retry time.

The fixer is wired as a sub-node. **Use a coding-capable model** (e.g., Claude Sonnet 4.6 or similar). Reconciling broken JSON against a schema with enums, ranges, and required fields is a structured-output / coding task, not a mechanical transform. Weak or generic models routinely produce another malformed retry, which defeats the point and burns tokens.

## "DO NOT wrap the output in a markdown code block"

This line is load-bearing. Models default to wrapping JSON in ```json ... ```, which breaks the parser. If you see parse failures on output that's clearly valid JSON inside a code block, this instruction is the fix.

You may also need it in your **main** system prompt if the main model wraps aggressively:

> "When responding with structured output, return raw JSON only. DO NOT wrap in markdown code blocks. DO NOT include any prose before or after the JSON."

## System prompt + parser: belt and suspenders

The parser tells the model the schema. The system prompt should ALSO tell it what shape to produce:

```
## Output Format
Respond with a JSON object matching this exact shape:
{ "score": 1-3 integer, "reason": "brief explanation" }

ONLY output the JSON. No prose, no markdown wrapping.
```

Repetition with the parser, but the model takes the system prompt seriously and reinforcement helps. The parser catches what slips through.

## Common parse failures and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| "Failed to parse output" but the text looks like JSON | Wrapped in markdown code block | Add "DO NOT wrap in markdown" to retry prompt and system prompt |
| Empty fields where the schema expects values | Model thinks it can omit when it doesn't know | Add "Use empty string '' or null for unknown fields, never omit" to the system prompt |
| Wrong types (number as string) | Schema example wasn't typed clearly | Use a real number in the example, not a string |
| Truncated JSON (unclosed brace) | Hit max_tokens mid-response | Increase max tokens, tighten the prompt to produce shorter output |
| Field names paraphrased ("Score" instead of "score") | Schema didn't fix the name | Be explicit in system prompt: "field names are exactly as shown" |
| `autoFix` retries forever | Fixer model is too weak for the schema | Swap in a coding-capable model (Sonnet-class), tighten the retry prompt |

## When NOT to use a parser

- **Free-form responses to the user.** Conversational chat replies don't need parsing.
- **Tool calls only, no final structured output.** If the user-visible output is text, no parser needed.
- **Simple key-value extraction.** A `Set` node with `JSON.parse($json.output)` handles trivial cases.

The parser is for when downstream nodes need to consume strict JSON.

## Cross-references

- For why and where to use agents at all: parent `SKILL.md`.
- For the system prompt half of the structured-output story: `SYSTEM_PROMPT.md`.
- For tools that themselves return structured output (vs the agent's final response): `TOOLS.md`.
