# Switch node: name your outputs and handle the fallback

The Switch node's `mode: 'rules'` exposes a per-rule `renameOutput: true` + `outputKey: '<name>'` pattern, plus an `options.fallbackOutput: 'extra'` + `options.renameFallbackOutput` pair for the default branch.

`get_node_types` shows these fields exist. It doesn't tell you the consequence of leaving them off:

- **No fallback output** = items that match no rule are *silently dropped*. No error, no warning, the workflow just loses data on the unmatched path. Always configure `options.fallbackOutput: 'extra'` with a meaningful `renameFallbackOutput` (`Unexpected`, `Default case`, `Other`).
- **Unnamed outputs** = the workflow is unreadable a month later. You see "0 / 1 / 2" without knowing which branch goes where. Set `renameOutput: true` + `outputKey: '<name>'` per rule.

Don't ship a Switch node with unnamed outputs and no fallback.
