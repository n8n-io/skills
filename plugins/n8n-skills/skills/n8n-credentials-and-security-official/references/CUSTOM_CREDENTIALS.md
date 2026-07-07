# Custom Auth credentials (`httpCustomAuth`)

The `httpCustomAuth` credential type covers auth shapes that don't fit n8n's standard built-ins: multiple headers, headers plus query params, or service-specific static values that need to live in the credential rather than the request.

For standard schemes (Bearer, Basic, generic Header Auth, OAuth2), use those built-in types. See `HTTP_REQUEST_WITH_AUTH.md`. Reach for `httpCustomAuth` only when a single built-in can't express the shape.

## When `httpCustomAuth` is the right answer

| Auth shape | Type to use |
|---|---|
| `Authorization: Bearer <token>` | `httpBearerAuth` (Bearer Auth) |
| `Authorization: Basic <base64>` | `httpBasicAuth` (Basic Auth) |
| Standard OAuth2 | `oAuth2Api` (Generic OAuth2) |
| Single custom header (`X-API-Key`) | `httpHeaderAuth` (Header Auth) |
| API key in `?api_key=...` query string | `httpCustomAuth` |
| Multiple headers (`X-API-Key` + `X-Tenant-ID`) | `httpCustomAuth` |
| Header + query combo | `httpCustomAuth` |

Rule: if the auth values are static and inject as headers or query params, `httpCustomAuth` works. If the auth value has to be computed per request (HMAC body signing, timestamp + nonce, JWT issuance, inbound webhook validation challenges), compute it with the **Crypto node** (`n8n-nodes-base.crypto`) and inject via expression. See `n8n-code-nodes-official` for the compute side.

Caveat with that workaround: the Crypto node's `secret` field doesn't bind to a credential, so the signing key has nowhere clean to live. The least-bad pattern is to keep the signing key in an `httpCustomAuth` credential and have the parent workflow pass it as an input to a sub-workflow that holds the Crypto node, rather than pasting the raw secret into the Crypto node's text field. This is a rough edge of the n8n credential system, not a clean pattern.

## Building with `httpCustomAuth`

Steps:

1. **In the n8n UI**, create a credential of type `Custom Auth` (`httpCustomAuth`).
2. The credential takes a JSON-shaped configuration:
   ```json
   {
     "headers": {
       "X-API-Key": "abc123",
       "X-Tenant-ID": "acme-prod"
     },
     "qs": {
       "version": "v2"
     }
   }
   ```
3. The user pastes the secret values into the JSON in the UI, and n8n encrypts the whole credential at rest.
4. Reference the credential from HTTP Request in your SDK code.

What gets injected:

- `headers`: each key/value becomes a request header.
- `qs`: each key/value becomes a query string parameter.
- Consulted per request, no refresh logic (static values).

## Asking the user

Give concrete instructions:

> "Create a credential in n8n of type `Custom Auth`. Paste this JSON, replacing the values:
>
> ```json
> { "headers": { "X-API-Key": "<your-key>", "X-Tenant-ID": "<your-tenant>" } }
> ```
>
> Save with name `Acme API (prod)`."

Specificity wins. "Make a custom credential" leaves the user picking among options.
