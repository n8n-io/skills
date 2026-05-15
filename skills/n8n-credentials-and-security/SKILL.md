---
name: n8n-credentials-and-security
description: Use when handling any auth, API keys, tokens, OAuth, bearer tokens, basic auth, or secret values in n8n workflows. Triggers on "API key", "token", "bearer", "OAuth", "secret", "auth", "credentials", "Authorization header", "x-api-key", or any node configuration that mentions a third-party service.
---

# n8n Credentials and Security

## Non-negotiables

1. **Secrets via the credential system, never in text fields or SDK code.** API keys, bearer tokens, OAuth secrets, passwords: all go through `newCredential()` or the node's `credentials` parameter. A Set node hardcoding a token and read via `{{$json.token}}` is a text field with extra steps.
2. **Don't ask the user for credential names, but DO tell them to verify each node.** The string in `newCredential('Label')` is cosmetic and does NOT bind to a specific stored credential. When the workflow opens, n8n auto-assigns the most recently edited credential of that type to every node, which silently picks the wrong one if the user has more than one (e.g., two Gmail accounts, prod + staging API keys). After building, always tell the user: "Open every node that uses a credential and confirm the right one is selected from the dropdown." Pick a sensible label (`'Gmail'`, `'OpenRouter'`, `'Acme API'`) and move on.
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
2. **You place the node, the user creates the credential from it.** You can't create credentials, the n8n MCP doesn't expose that. Tell the user: "I'll add the node configured for the right credential type (e.g. `Bearer Auth` for bearer tokens, `Header Auth` for other custom auth headers). When you open it, click the credential dropdown and choose 'Create new credential', and n8n will prompt you for the token there." The credential field on the node will either be empty (no credential of that type exists yet) or auto-filled with the user's most recently edited one of that type (see non-negotiable #2).
3. **For programmatic credential creation**, the MCP surface may be limited. See `n8n-extending-mcp` for wrapping n8n's credential APIs. The user must provide the secret value, and you should not be the persistent home for it.
4. **Treat the pasted secret as compromised, and tell the user to rotate it.** Don't soften this. The token has been transmitted to the LLM provider, may persist in chat history, transcripts, and cache layers, and is now outside the user's control. Tell them: "Rotate this token as soon as the new credential is set up in n8n. Pasting a secret into chat exposes it beyond this conversation. Treat it as leaked, not just visible."

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

