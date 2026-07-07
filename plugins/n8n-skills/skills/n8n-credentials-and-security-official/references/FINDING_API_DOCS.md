# Finding API docs

Before configuring HTTP Request for a non-native service, you need:

1. **Base URL.**
2. **Auth scheme** (Bearer, Basic, Custom Header, OAuth2, signed, etc.).
3. **Endpoint shape** (path, method, body, query params).
4. Common **error responses** for error handling.

## Where to look (in order)

1. **Official API docs.** Canonical. Usually `docs.<service>.com` or `developer.<service>.com`.
2. **OpenAPI/Swagger spec.** Many services publish `openapi.json` or `swagger.json`, a complete machine-readable description.
3. **Postman collections.** Public workspaces often have working examples with exact headers and body shapes.
4. **GitHub repos.** The service's official SDK reveals the exact auth shape in source.
5. **The user's existing setup.** If they've used the API in another tool (workflow, script, Postman), ask for the snippet. Working code beats generic docs.

## What to extract from the docs

For every operation the user wants to perform, record:

```
Base URL:            https://api.acme.com/v1
Auth:                Bearer (Authorization header)
                     OR API key (X-API-Key header)
                     OR OAuth2 (auth URL: ..., token URL: ..., scopes: ...)
Operation:           List widgets
  Method:            GET
  Path:              /widgets
  Query params:      ?limit=N&cursor=X (optional)
  Response shape:    { data: [...], next_cursor: string }
  Common errors:     401 (unauthorized), 429 (rate limit, with Retry-After header)
```

With this, you configure HTTP Request precisely instead of guessing.

## When the docs are bad or missing

Workarounds:

- **The web UI uses HTTP under the hood.** Open dev tools → Network tab, capture requests, reverse-engineer. Watch out for short-lived session cookies vs. long-lived API tokens, which use different auth schemes.
- **Ask the user.** Even a `curl` command from a colleague is useful.
- **Try it.** Fast-feedback iteration (request → error → adjust) beats stalling on incomplete docs. Use `test_workflow` to avoid side effects.

## Auth scheme detection

A few common signals:

| In docs / examples | Likely auth scheme | n8n credential type |
|---|---|---|
| `Authorization: Bearer xxx` | Bearer token | Bearer Auth (`httpBearerAuth`) |
| `Authorization: Token xxx` | Token (similar to Bearer) | Header Auth (no `Token` built-in) |
| `Authorization: Basic xxx` | Basic Auth | Basic Auth |
| `X-API-Key: xxx` | API key in custom header | Header Auth |
| `?api_key=xxx` | API key in query string | Query Auth or Custom Auth |
| Two static headers (key + tenant, key + version) | Multi-header auth | `httpCustomAuth` |
| Auth flow with consent screen | OAuth2 | Generic OAuth2 |
| `aws-sigv4` | AWS Signature v4 | Custom, see service-specific docs |
| Two headers (key + signature) | Per-request signing | Crypto node + expression injection. See `CUSTOM_CREDENTIALS.md` |
| WebSocket upgrade with subprotocol auth | WebSocket auth | Outside HTTP Request scope |


## Pagination

Common shapes:

- **Cursor:** `?cursor=X`, response has `next_cursor`. Loop until null/missing.
- **Page-based:** `?page=N&per_page=K`, response has `total_pages` or stop when fewer than `K` returned.
- **Offset:** `?offset=N&limit=K`, response has `total` or stop when fewer than `K` returned.
- **Link header:** `Link: <...>; rel="next"`. Loop until no `next` link.

Note which shape the API uses *before* writing the workflow. HTTP Request has built-in pagination for all four.

## Rate limits

Look for:

- Documented rate (e.g., "100 requests per minute").
- 429 responses with `Retry-After` headers.
- `X-RateLimit-Remaining` / `X-RateLimit-Reset` headers.

Error handling:

- Wire HTTP Request's error output to a Wait node (delay = `Retry-After`), loop back.
- Or use HTTP Request's `retryOnFail` parameter.

One-off scripts can ignore rate limits. Scheduled/production workflows can't.

## Sandbox vs. production

Many APIs offer sandboxes with different credentials and base URLs.

- Ask if sandbox credentials are available, since they're safer for development.
- Name credentials clearly (`Acme API (sandbox)` vs `Acme API (prod)`).
- Reference the right one per workflow.

Don't develop against production unless explicitly chosen.

## What to give back to the user

After research:

> "Acme's API uses Bearer auth at `https://api.acme.com/v1`. To list widgets, `GET /widgets` with optional `?limit=N&cursor=X`. Cursor-based pagination via `next_cursor`. Rate limit: 100 req/min with 429 responses.
>
> Create a credential of type `Bearer Auth` and paste the token in (n8n adds the `Bearer ` prefix and `Authorization` header for you)."

Concrete and specific. The user provides the token, and you wire the rest.
