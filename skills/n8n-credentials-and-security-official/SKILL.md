---
name: n8n-credentials-and-security-official
description: Use when handling any auth, API keys, tokens, OAuth, bearer tokens, basic auth, or secret values in n8n workflows. Triggers on "API key", "token", "bearer", "OAuth", "secret", "auth", "credentials", "Authorization header", "x-api-key", or any node configuration that mentions a third-party service.
---

# n8n Credentials and Security

## Non-negotiables

1. **Secrets via the credential system, never in text fields or SDK code.** API keys, bearer tokens, OAuth secrets, passwords: all go through `newCredential()` or the node's `credentials` parameter. A Set node hardcoding a token and read via `{{$json.token}}` is a text field with extra steps.
2. **List credentials, then bind by ID.** Call `list_credentials({type})` before configuring an auth-needing node. One match: bind via 2-arg `newCredential('Label', 'credId')` at create time, or `setNodeCredential` op on `update_workflow`. Multiple matches: ask the user which. The one-arg `newCredential('Label')` is a placeholder; n8n auto-assigns the most recently edited credential of that type and silently picks wrong when the user has multiples.
3. **Credential creation is the user's job, not yours.** The n8n MCP doesn't expose credential creation. Tell the user the exact credential *type* to create in the UI, then reference it by label in your node config. Don't attempt to create credentials programmatically and don't accept secrets in chat to "set up later".

## Strong defaults

- **Use native credentials when available.** Every native node (Slack, Gmail, Postgres, OpenAI, etc.) has a credential type. Don't reach for generic credential types when a native option exists.
- **For multi-header or header-plus-query auth shapes**, use the `httpCustomAuth` credential type. See `references/CUSTOM_CREDENTIALS.md`.

## The credential system

In n8n, credentials are first-class objects:

- Stored encrypted at rest in the n8n database.
- Referenced by ID from nodes that need them.
- Scoped to projects (Cloud & enterprise) or shared globally (some self-hosted setups).
- Identified by a type slug (googleSheetsOAuth2Api, slackApi, httpHeaderAuth). The slug is what nodes reference and what determines which auth fields the credential collects.

A node that needs auth has a `credentials` parameter pointing to a credential ID + type. Secret values never appear in workflow JSON. Exporting a workflow leaks the *reference*, not the secret.

For the full model (SDK resolution, rotation, project scoping), see `references/CREDENTIAL_SYSTEM.md`.

## Decision tree: how to authenticate this thing

```
Need to call an external service?
├── Native credential exists (Slack, Gmail, OpenAI, Postgres, ...)?
│   └── Use the native node + its credential type. Done.
│
├── Service is "standard-shaped" (REST + Bearer/Basic/OAuth)?
│   ├── Configure HTTP Request with one of the built-in auth types:
│   │   - Generic OAuth2
│   │   - Header Auth
|   |   - Bearer Auth (same as header auth but with only field being for actual token)
│   │   - Basic Auth
│   │   - Custom Auth
│   └── See references/HTTP_REQUEST_WITH_AUTH.md
│
└── Service needs multiple static headers, or headers plus query params?
    └── Use the httpCustomAuth credential type.
        See references/CUSTOM_CREDENTIALS.md
```

## When the user pastes a secret into a chat

This happens. The user types something like:

> "Set up a workflow to call Acme API with bearer `sk-abc123def456`"

What to do:

1. **Don't put the token in a text field, even temporarily.** A Set node that hardcodes the value and is referenced via `{{$json.token}}` is a text field with extra steps.
2. **Bind to an existing credential if possible.** `list_credentials({type})` first; if a match exists, bind via `setNodeCredential` and tell the user which one you used. If none exists, tell them to create one in the UI (Bearer Auth for bearer tokens, Header Auth for custom headers, etc.). Credential creation is still UI-only.
3. **Treat the pasted secret as compromised, and tell the user to rotate it.** Don't soften this. The token has been transmitted to the LLM provider, may persist in chat history, transcripts, and cache layers. Tell them: "Rotate this token as soon as the new credential is set up. Treat it as leaked."

## When no native node exists

Common case: the user wants a service n8n has no node for. Use HTTP Request with appropriate auth.

- `references/FINDING_API_DOCS.md`: discovering auth scheme, base URL, common shapes.
- `references/HTTP_REQUEST_WITH_AUTH.md`: wiring HTTP Request to a credential.
- `references/CUSTOM_CREDENTIALS.md`: when built-in auth types don't fit.

## Reference files

| File | Read when |
|---|---|
| `references/CREDENTIAL_SYSTEM.md` | You need to understand how credentials are stored, referenced, scoped, or rotated |
| `references/CUSTOM_CREDENTIALS.md` | Multi-header / header-plus-query auth in one credential, or per-request signing patterns (HMAC, JWT, webhook validation) |
| `references/HTTP_REQUEST_WITH_AUTH.md` | Configuring HTTP Request with auth: Bearer, Basic, OAuth, Header Auth |
| `references/FINDING_API_DOCS.md` | The user mentioned a service you don't have node-level knowledge of |

## Anti-patterns

| Anti-pattern | What goes wrong | Fix |
|---|---|---|
| Pasting `sk-...` into HTTP Request's `Authorization` header value field | Token in plain text in the workflow JSON, leaks on export, copy, screenshot | Use a credential: `Bearer Auth` for bearer tokens, `Header Auth` for other custom auth schemes |
| Storing token in a Set node and referencing via expression | Same problem, value lives in workflow JSON | Same fix: credential, not a Set node |
| Storing a secret in `$vars.X` and reading it as the auth value | Not encrypted at rest, leaks in exports, no rotation | Use the right credential type (`httpBearerAuth`, `httpHeaderAuth`, `httpCustomAuth`, or the native one). For inbound webhook auth, use the trigger's `authentication` field, not an IF on `$vars.token` |
| Reaching for `$env.X` to read a secret during custom auth setup | Doesn't work, throws at runtime | Use a credential of the appropriate type |
| Using HTTP Request when a native node exists | Loses auto-refresh on OAuth, loses native error handling, more code | Use the native node |
| Hardcoding credentials in SDK code (`new HttpRequest({ headers: { Authorization: 'Bearer xxx' } })`) | Same leak surface | Use `newCredential()` in SDK code |
| Asking the user to create a credential without naming the credential *type* | User picks the wrong type, auth fails confusingly | Always specify: "create a credential of type `<exact type name>`" |

