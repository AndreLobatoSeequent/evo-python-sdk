---
name: evo-cli
description: Use this skill when the user wants to interact with the Seequent Evo platform through the `evo` CLI — geoscience objects, block models, workspaces, files, compute jobs, or organization administration. Trigger for explicit references to Evo, Seequent Evo, the evo CLI, Evo workspaces/objects/block models/compute jobs.
metadata:
  version: "0.1.0"
  tags: evo,seequent,geoscience,block-models,workspaces,compute
  alwaysApply: "false"
---

# Evo CLI

`evo` is the command-line interface for the Seequent Evo platform: geoscience objects, block models, workspaces, files, compute jobs, and organization administration.

## Discover commands

`evo` is self-describing. Prefer these over guessing flags:

```powershell
evo agent info                          # current auth/agent/selection state
evo agent schema                        # full JSON command reference
evo agent schema --compact              # smaller schema, fewer tokens
evo agent schema --command blockmodels  # schema for one command group
evo <command> --help
```

Every command accepts `--format json`; agent-mode callers (Claude Code, Cursor, etc.) already get JSON output by default, so you rarely need to pass it explicitly.

## Authenticate and select a workspace

Most commands need a configured client ID, a login, and an active organization/hub/workspace selection. Check `evo auth status` before assuming any of these are done. First-time setup:

```powershell
evo auth configure                           # provides instructions on registering a client ID
evo auth configure --client-id <client-id>   # one-time, registers the app
evo auth login                               # opens a browser to sign in
```

Once logged in, select an organization/hub and workspace:

```powershell
evo instances list
evo instances select --org-id <id> --hub-code <code>
evo workspaces list
evo workspace select <workspace-id>
```

## Quick reference

| Task | Command |
|---|---|
| Check auth status | `evo auth status` |
| Register a client ID / log in | `evo auth configure --client-id <id>` then `evo auth login` |
| List orgs/hubs | `evo instances list` |
| Select org/hub | `evo instances select --org-id <id> --hub-code <code>` |
| List workspaces | `evo workspaces list` |
| Select a workspace | `evo workspace select <workspace-id>` |
| List geoscience objects | `evo objects list` |
| Download an object | `evo objects download <id>` |
| List block models | `evo blockmodels list` |
| Inspect block model columns | `evo blockmodels columns list <block-model-id>` |
| Upload a file | `evo files upload <path>` |
| List files | `evo files list` |
| Submit a compute job | `evo compute job submit ...` |
| List compute jobs | `evo compute job list` |
| Manage instance users (admin) | `evo admin users list` |

Run `evo <command> --help` or `evo agent schema --command <command>` for the full set of flags before guessing; do not invent options that no `--help` output confirms.

## Error handling

- If auth is missing, unconfigured, or expired, ask the user to run `evo auth configure`/`evo auth login` rather than working around it — don't guess a client ID.
- Treat destructive commands (delete, cancel) as requiring explicit user confirmation before running.
