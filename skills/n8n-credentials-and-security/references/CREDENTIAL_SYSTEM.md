# How the credential system works

Credentials in n8n are first-class, encrypted, referenced-by-ID objects.

## Storage model

- **At rest:** encrypted in n8n's database with a key derived from `N8N_ENCRYPTION_KEY` (self-hosted, managed on Cloud).
- **In memory:** decrypted only when a node executes and needs to authenticate.
- **In workflow JSON:** never present. The workflow references credentials by `id` and `name`, and secret values are not exported.

The key property: workflow JSON can be safely shared (Git, chat, screenshots) without leaking secrets, *as long as you used the credential system instead of pasting values into text fields*.

## Reference shape

In the workflow JSON, a node that uses credentials has a parameter shaped like:

```json
{
  "credentials": {
    "<credentialType>": {
      "id": "abc123",
      "name": "Acme API (prod)"
    }
  }
}
```

- `<credentialType>`: the exact internal type string (e.g., `slackApi`, `googleSheetsOAuth2Api`, `httpHeaderAuth`).
- `id`: the credential's UUID in the database.
- `name`: the user's display name for the credential.

Both are exported. Neither is sensitive, and knowing the ID does not let an attacker authenticate.

## In SDK code

When writing workflow SDK code, reference credentials via `newCredential()`:

```ts
const slack = node({
  type: 'n8n-nodes-base.slack',
  config: {
    parameters: { /* ...other params... */ },
    credentials: { slackApi: newCredential('Slack') },
  },
})
```

The shape that matters:

- **The credential TYPE (`slackApi`, `gmailOAuth2`, `httpHeaderAuth`, etc.) IS load-bearing.** It must match what the node expects. Use the exact n8n type name as shown in the credential picker: "Slack API" and "Slack OAuth2" are different, and "Slack" alone is ambiguous. If the user's request is ambiguous about which auth flavor, ask before guessing.
<!-- TEMPORARY: change once the mcp can select credentials -->
- **The string argument to `newCredential('...')` is cosmetic.** A placeholder label in workflow JSON. It does NOT bind to a specific stored credential.

At import time, every node that needs a credential of a given type gets auto-assigned the user's *most recently edited* credential of that type. The dropdown is there for the user to override, but the default is silent and not based on the `newCredential('...')` label. With one credential of a type, this is fine. With multiple (prod + staging keys, two Gmail accounts), the wrong one is picked silently and auth either fails or worse, succeeds against the wrong account.

Implications:

- **Don't ask the user for their existing credential's name before building.** Pick a sensible label and move on.
- **Tell the user after building**: "Open every node that uses a credential and confirm the right one is selected from the dropdown. n8n auto-assigns the most recently edited one of that type, which may not be what you want."
- **Don't worry about credential collisions across workflows.** Labels don't share state.


## Project scoping

On n8n Cloud and self-hosted with project support:

- Credentials are scoped to projects.
- Project A's workflow can't reference project B's credential without sharing.
- Sharing is opt-in via the UI.

When the user mentions "the prod credential," confirm the project. If multiple projects have similar names, ask before guessing.

## Rotation

When a secret value rotates:

- Update the credential in the n8n UI, and the `id` stays the same.
- Workflows referencing that `id` keep working without redeployment.
- This is why credentials are ID-referenced: rotation doesn't break references.

If the user says "I rotated the API key, why is the workflow still failing?", confirm they updated the credential in n8n (not just rotated upstream). Both sides need to match.

## Discovery

The MCP's surface for listing credentials is limited. The `n8n-extending-mcp` pattern wraps n8n's credentials API as an MCP-callable tool. Once that exists, call it to discover credentials by type. Without it, ask the user.

