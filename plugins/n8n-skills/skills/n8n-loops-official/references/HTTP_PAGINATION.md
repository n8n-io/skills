# HTTP Request pagination

The HTTP Request node has built-in pagination. Most reinvent it with `Loop Over Items` and manual `$pageCount`. The built-in version is simpler, more robust, and yields a single output array of all pages' items.

Use it for any paginated API.

## Where to find it

HTTP Request config: **Add Option** → **Pagination**.

In SDK terms, under `options.pagination`:

```ts
{
    type: 'n8n-nodes-base.httpRequest',
    parameters: {
        method: 'GET',
        url: 'https://api.example.com/items',
        options: {
            pagination: {
                pagination: {
                    paginationMode: 'updateAParameterInEachRequest',
                    // ...mode-specific config
                },
            },
        },
    },
}
```

## The three pagination modes

### Mode 1: Update a Parameter in Each Request

For APIs using a page number, offset, or cursor as a query/body/header parameter.

```ts
{
    paginationMode: 'updateAParameterInEachRequest',
    parameters: {
        parameters: [
            {
                type: 'qs',            // 'qs' (query string) | 'body' | 'headers'.
                                       //  UI label is "Query" but the internal value is 'qs'.
                name: 'page',
                value: '={{ $pageCount + 1 }}',
            },
        ],
    },
}
```

Key points:

- **`$pageCount` is 0-indexed.** Most APIs page from 1, so use `$pageCount + 1`. If yours pages from 0, use `$pageCount` directly.
- **Paginate multiple parameters together** if needed (e.g., `offset` + `limit`).
- For cursor-based APIs, use `$response.body.<cursor_field>` as the value.

### Mode 2: Response Contains Next URL

For responses with a `next` link (Link header, `_links.next.href`, `nextPageUrl`, etc.).

```ts
{
    paginationMode: 'responseContainsNextURL',
    nextURL: '={{ $response.body.next_page_url }}',
}
```

Point `nextURL` at the response field via expression. The node calls that URL next.

**Termination still goes through `paginationCompleteWhen`** (default `responseIsEmpty`). For APIs whose final page has an empty body, the default works without extra config. For APIs that always return a populated body but drop the `next` field on the last page, set `paginationCompleteWhen: 'other'` with a `completeExpression` checking for the absent field. If `nextURL` evaluates to an empty string, the node throws an "invalid URL" error rather than stopping cleanly.

### Mode 3: Off

Default. One request, one response.

## Page size

Page size is a normal query parameter, *not* inside the pagination block. Add via **Send Query Parameters**:

```ts
queryParameters: {
    parameters: [
        { name: 'limit', value: '100' },
    ],
}
```

The pagination block bumps the page param while `limit` stays constant.

## Termination conditions

**Pagination Complete When** option:

- **`responseIsEmpty`** (default): stops on empty response body.
- **`receiveSpecificStatusCodes`**: stops on listed status codes (e.g., `[404]`).
- **`other`**: provide a `completeExpression` that's true when done.

Custom completion example:

```ts
{
    paginationMode: 'updateAParameterInEachRequest',
    completeExpression: '={{ $response.body.items.length === 0 }}',
    // ...
}
```

Next-URL mode terminates naturally when the expression returns falsy. No extra config needed in most cases.

## Limits and safety

- **`limitPagesFetched`** (boolean) + **`maxRequests`** (number): hard cap. Set this in production. A misbehaving API (returning the same `next` URL) without a cap = infinite requests.
- **`requestInterval`** (ms): delay between requests. Use for rate-limited APIs (e.g., `100` = 10/s, `500` = 2/s).

Reasonable defaults for unknown APIs:

```ts
{
    paginationMode: 'updateAParameterInEachRequest',
    parameters: { /* ... */ },
    limitPagesFetched: true,
    maxRequests: 50,           // hard ceiling
    requestInterval: 200,      // 5 req/s
}
```

50 pages × 100 items = 5,000 items, enough for most workflows. Adjust as needed.

## Built-in expression variables

- **`$pageCount`**: pages already fetched (0 on first request).
- **`$request`**: the request that just went out (URL, headers, body, query).
- **`$response`**: previous call's response. `$response.body`, `$response.headers`, `$response.statusCode`.

`$response` is the workhorse for non-trivial pagination expressions.

## Output shape

The HTTP Request node with pagination returns a *single* output array of all pages' items, concatenated. No flatten/merge needed.

If items are wrapped in an envelope (`{ data: [...], meta: {...} }`), each page's response is one output item. For a flat list, flatten with a downstream `Split Out` node or an `Edit Fields` expression that pulls `$json.data`. (V3 of the HTTP Request node has no built-in `splitIntoItems` option, that was V1/V2 only.)

## Response Format (relevant when paginating non-JSON content)

Separate from the Pagination block, the **Response > Response Format** option controls how the body is parsed:

```ts
options: {
    response: {
        response: {
            responseFormat: 'autodetect',   // 'autodetect' | 'json' | 'text' | 'file'
            outputPropertyName: 'data',     // required when responseFormat is 'text' or 'file'
        },
    },
}
```

- `'autodetect'` (default): node infers from `Content-Type`.
- `'json'`: forces JSON parse.
- `'text'`: returns the raw body as a string in the field named by `outputPropertyName` (default `'data'`). Useful when paginating an HTML site for scraping, or any non-JSON paginated source.
- `'file'`: writes the body to binary, typically for downloading paged file ranges.

Pagination expressions still see `$response.body` either way, so a `text`-formatted response works with regex-based `nextURL` extraction (e.g., parsing a Link header or scraping a "next" anchor from HTML).

## Examples

### Github-style: page parameter, stops on empty

```ts
{
    method: 'GET',
    url: 'https://api.github.com/repos/{owner}/{repo}/issues',
    sendQuery: true,
    queryParameters: {
        parameters: [
            { name: 'per_page', value: '100' },
        ],
    },
    options: {
        pagination: {
            pagination: {
                paginationMode: 'updateAParameterInEachRequest',
                parameters: {
                    parameters: [
                        { type: 'qs', name: 'page', value: '={{ $pageCount + 1 }}' },
                    ],
                },
                paginationCompleteWhen: 'responseIsEmpty',
                limitPagesFetched: true,
                maxRequests: 100,
            },
        },
    },
}
```

### Stripe-style: cursor in response, fetched via `starting_after`

```ts
{
    method: 'GET',
    url: 'https://api.stripe.com/v1/customers',
    sendQuery: true,
    queryParameters: {
        parameters: [{ name: 'limit', value: '100' }],
    },
    options: {
        pagination: {
            pagination: {
                paginationMode: 'updateAParameterInEachRequest',
                parameters: {
                    parameters: [
                        {
                            type: 'qs',
                            name: 'starting_after',
                            value: '={{ $response.body.data[$response.body.data.length - 1].id }}',
                        },
                    ],
                },
                paginationCompleteWhen: 'other',
                completeExpression: '={{ !$response.body.has_more }}',
            },
        },
    },
}
```

Reads the last item's `id` from the previous response as `starting_after`. Stops when `has_more` is false.

### Link header (RFC 5988)

```ts
{
    options: {
        pagination: {
            pagination: {
                paginationMode: 'responseContainsNextURL',
                nextURL: `={{
                    (() => {
                        const link = $response.headers.link ?? '';
                        const match = link.match(/<([^>]+)>;\\s*rel="next"/);
                        return match ? match[1] : null;
                    })()
                }}`,
            },
        },
    },
}
```

Returns null when there's no `next` rel, and pagination stops.

## Common mistakes

### Hand-rolling pagination with `Loop Over Items` and `$pageCount`

If the API has a page parameter or next URL, the built-in is simpler and less error-prone. Use `Loop Over Items` only when the API does something genuinely odd (multi-step requests per page, dynamic auth refresh between pages).

### Forgetting `limitPagesFetched`

A misconfigured next-URL expression returning the same URL = infinite requests. Always set a max in production.

### `$pageCount` off by one

`$pageCount` is 0 on the first call. APIs paging from 1 need `$pageCount + 1`. Easy to miss: page 1 works, page 2 returns page 1's response.

### Not splitting items

`{ data: [...] }` envelopes make each page one output item. Most downstream code wants a flat array. Flatten with a downstream `Split Out` node or an `Edit Fields` expression. (V3's HTTP Request has no built-in split option.)

### Pagination without a stop condition

Default "response is empty" works for most APIs. For non-empty envelopes with empty `data` on the last page, use `paginationCompleteWhen: 'other'` with `completeExpression` checking `data.length === 0`.

## Cross-references

- For non-HTTP looping (rate-limited fan-out, batched bulk writes), see `LOOP_OVER_ITEMS.md`.
- For default per-item iteration and `executeOnce`, see the parent `SKILL.md`.
- For general HTTP node config (auth, body, headers), see `n8n-node-configuration-official` `HTTP_NODES.md`.
