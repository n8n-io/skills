# n8n for Google Antigravity

Build, test, and manage n8n workflows with the 15 official skills and your instance MCP server.

## Requirements

Use a current Antigravity release and an n8n instance with **Settings > Instance-level MCP** enabled. MCP requires n8n 2.2.0 or later. Newer tools depend on the n8n version, enabled features, and granted scopes.

## Install and connect

```bash
git clone https://github.com/n8n-io/skills.git
cd skills
agy plugin validate --strict .
agy plugin install .
```

1. Open **Customizations > Installed** in Antigravity. Enable **n8n**. Restart the app if it does not appear.
2. Enter the full **n8n MCP server URL** from n8n's settings, including `/mcp-server/http` and any instance subpath. Use HTTPS for remote instances.
3. Authenticate the bundled server. Sign in to n8n and select the permissions you need. If Antigravity asks for an authorization code, copy it from the callback page.
4. Start a conversation and ask: **Find workflows on my n8n instance.**

Antigravity handles OAuth directly. An always-on plugin rule points to the shared skills. No Node.js installation or authentication proxy is required.

To change instances, open the plugin's **MCP** tab and configure `n8n-mcp`. Its tool namespace is `n8n-skills_n8n-mcp`. Save the full endpoint, then sign in from **Accounts**. Disable any duplicate connection to the same instance.

## Troubleshooting

| Symptom | Check |
|---|---|
| Plugin stays disabled | Fill in its MCP URL before enabling it. |
| Connection fails | Check the complete endpoint, certificate, network access, and instance-level MCP setting. |
| Sign-in fails | Authenticate again. Replacing a database at the same URL can leave a cached client registration; use separate endpoints for disposable instances. Reinstalling does not reset that registration. |
| Workflows or tools are missing | Check project access, workflow MCP access, selected scopes, and n8n version. Read-only grants hide write and execution tools. |
| Skills are not used | Confirm the plugin is enabled. Start with `/using-n8n-skills-official` to load the router explicitly. |

## Tested scope

Native OAuth and workflow operations were tested on macOS with Antigravity App 2.30.0 and self-hosted n8n 2.47.3. The native rule also loads the router and capability skills. Package checks run on macOS, Windows, and Linux.

Desktop Windows/Linux, n8n Cloud, remote HTTPS/subpaths, actual app compaction, and reauthorization after revocation remain untested. MCP Apps, elicitation, remote skill resources, full Agent operations, and long-running recovery need separate tests. Tool discovery does not prove support for these optional protocols.

## Update and remove

To update, run `git pull` in the clone, then validate and install again with the commands above. Restart Antigravity and check the connection.

To remove the plugin, run `agy plugin uninstall n8n-skills`. Revoke its connection in n8n's MCP settings to remove its OAuth grant. Uninstalling the plugin does not revoke that grant.

Sources: [Google plugin setup](https://antigravity.google/docs/plugins), [plugin rules](https://antigravity.google/docs/build-plugins/#rules), [n8n MCP setup](https://docs.n8n.io/build/ways-of-building-workflows/connect-to-n8n-mcp-server/).
