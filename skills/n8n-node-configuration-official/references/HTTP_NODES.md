# HTTP Request: gotchas and patterns

The exact parameter shape evolves across versions. Always `get_node_types` for the canonical shape. This file covers what's *not* in the type definition: security rules, decision-making, engine caps, runtime gotchas.

## Always inspect first

`get_node_types([{ name: 'httpRequest' }])`. Build against the live shape, not memory.

## Auth: the #1 source of HTTP Request bugs

Three modes, each with different required follow-ups (`get_node_types` shows them):

- **`'none'`**: unauthenticated.
- **`'predefinedCredentialType'`**: n8n has a built-in credential type for this service (Slack, Notion, etc.). Use this when the service is already supported.
- **`'genericCredentialType'`**: pick from the long tail of generic auth types (header, basic, OAuth2, query, custom). Use this for services without a native node.

Common mistakes:
- Setting `credentials` but leaving `authentication: 'none'`: credentials silently ignored.
- Putting tokens in `headerParameters` / `queryParameters` / `bodyParameters` instead of credentials: this puts them in plain text in the workflow. See `n8n-credentials-and-security-official`.
- Using `genericCredentialType` when a `predefinedCredentialType` exists for the service. Predefined types are usually easier to set up (the OAuth flow, refresh handling, etc. is wired for you).

For the full auth pattern, see `n8n-credentials-and-security-official`'s `HTTP_REQUEST_WITH_AUTH.md`.

## Body and query: discriminators matter

Both body and query have a 2-level discriminator pattern:

- `sendBody: true` + `contentType` (json / form-urlencoded / multipart-form-data / raw / binaryData) + `specifyBody` (keypair / json / string for some content types).
- `sendQuery: true` + `specifyQuery` (keypair / json).

Setting one path's fields with the other path's discriminator silently does nothing. Always inspect via `get_node_types` for the operation you're configuring.

## Pagination

Built-in. See `n8n-loops-official` `HTTP_PAGINATION.md` for the full matrix. Don't reinvent with `Loop Over Items` + `$pageCount` unless the API does something the modes can't express.

## Retry on fail

`retryOnFail: true` enables it. The engine retries on **all** errors.

- `maxTries`: Default to 3.
- `waitBetweenTries`: Default to 5000.

## Timeouts

Runtime default is **5 minutes** when `options.timeout` is unset. The UI default if you toggle the option on is 10 seconds. Set explicitly for untrusted/external APIs (e.g., 10000ms = 10s) so a hung request doesn't stall the workflow.

## Response handling

Three options under `options.response.response`:

- `fullResponse: true`: include headers + status code, not just body. Useful for `X-Rate-Limit-Remaining` and similar.
- `neverError: true`: don't throw on non-2xx. The error body flows through and you check status manually. Useful when handling errors in workflow logic instead of via the error output.
- `responseFormat`: `'autodetect'` (default) / `'json'` / `'text'` / `'file'`. `'text'` and `'file'` require `outputPropertyName`.

