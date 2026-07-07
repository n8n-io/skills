# HTTP Request with auth

When no native node exists, HTTP Request is the right tool. This covers wiring it to a credential cleanly.

For multi-header or header-plus-query auth shapes, see `CUSTOM_CREDENTIALS.md`.

## The pattern

1. **Create the credential in the n8n UI** of the appropriate type.
2. **In HTTP Request**, set `Authentication`. Prefer "Predefined Credential Type" if n8n has one for the service (the OAuth flow, refresh, base URL handling are all wired for you). Fall back to "Generic Credential Type" only when no predefined type exists.
3. **Select the credential** from the dropdown, or reference it via `newCredential()` in SDK code.
4. **Don't put secret values in URL/header text fields.** They should reference the credential.

## Picking the right auth type

| Service auth | n8n credential type | Notes |
|---|---|---|
| `Authorization: Bearer <token>` | `httpBearerAuth` (Bearer Auth) | Paste the raw token; n8n adds the `Bearer ` prefix and `Authorization` header automatically |
| `Authorization: Basic <base64>` | `httpBasicAuth` (Basic Auth) | n8n base64-encodes the username:password |
| Custom header (`X-API-Key`) | `httpHeaderAuth` (Header Auth) | Header name: `X-API-Key`, value: the key |
| API key in query string (`?api_key=xxx`) | `httpQueryAuth` (Query Auth) when available, otherwise `httpCustomAuth` | |
| Standard OAuth2 | `oAuth2Api` (Generic OAuth2) | Configure auth/token URLs and scopes, and n8n handles the flow |
| Multiple headers + query params | `httpCustomAuth` | See `CUSTOM_CREDENTIALS.md` |
| HMAC / per-request signing | No credential type alone | Crypto node + expression injection. See `CUSTOM_CREDENTIALS.md` and `n8n-code-nodes-official` |

## SDK shape

In SDK code:

```ts
// credId from list_credentials({ type: 'httpHeaderAuth' })
const cred = newCredential('Acme API (prod)', '<credId>')

const fetchAcme = node({
  type: 'n8n-nodes-base.httpRequest',
  config: {
    parameters: {
      method: 'GET',
      url: 'https://api.acme.com/v1/widgets',
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
    },
    credentials: { httpHeaderAuth: cred },
  },
})
```

Key parameters:

- `authentication`: `'predefinedCredentialType'` when n8n has one for the service (less setup, refresh handled), otherwise `'genericCredentialType'` with the matching `genericAuthType`.
- `genericAuthType`: credential type string, must match the credential (`httpBearerAuth`, `httpHeaderAuth`, `httpBasicAuth`, `oAuth2Api`, `httpCustomAuth`, etc.).
- `credentials`: the reference from `newCredential()`.

## Common mistakes

### Token pasted into the URL

```ts
// DON'T
url: `https://api.acme.com/v1/widgets?api_key=sk-abc123`
```

Token now lives in workflow JSON. Fix: credential of type Query Auth or Custom Auth.

### Token pasted into a header value field

```ts
// DON'T
headerParameters: {
  parameters: [
    { name: 'Authorization', value: 'Bearer sk-abc123' }
  ]
}
```

Fix: a Bearer Auth credential (or Header Auth for non-bearer schemes) setting the same header. Don't add it to `headerParameters`.

### Mixing `headerParameters` with credential-injected headers

If the credential injects `Authorization` (Bearer Auth, Header Auth, or Bearer-style OAuth2), don't *also* add `Authorization` in `headerParameters`. Conflict, undefined behavior.

For multiple headers (e.g., `Authorization` + `X-Tenant-ID`), use one `httpCustomAuth` credential. See `CUSTOM_CREDENTIALS.md`.

### Forgetting to switch `authentication` from `none`

The default is often `'none'`. Setting `genericAuthType` and `credentials` without flipping `authentication` means the credential is silently ignored. Request goes unauthenticated, API returns 401.

Verify via `get_node_types` and `get_workflow_details` that both `authentication` and `credentials` are set.

### Storing OAuth2 access tokens in a Header Auth credential

`oAuth2Api` handles the full OAuth2 flow (authorization, token exchange, refresh). Storing access tokens in Header Auth means they expire without refresh, and the workflow starts failing silently.

For OAuth2, use `oAuth2Api`. Always.

## "Just put the key in for now"

Don't. "Fix it later" is the leak path. A credential takes 30 seconds.

If the user explicitly authorizes a one-off (throwaway test workflow):

- Mark `archived` or tag `throwaway`.
- Tell them to clean up before sharing, exporting, or persisting.
- Don't publish a workflow with inlined secrets. Keep inactive until the credential exists.

## Verifying it landed

After `create_workflow_from_code` or `update_workflow`, run `get_workflow_details` and check:

1. `parameters.authentication` is set (not `'none'`).
2. `parameters.genericAuthType` matches the credential type.
3. `credentials.<type>.id` and `.name` match the intended credential.
4. **No secret-shaped strings** in `parameters`: no Bearer prefixes, no token prefixes, no 32+ char random strings outside `credentials` references.

If any fails, auth is misconfigured before the request fires.
