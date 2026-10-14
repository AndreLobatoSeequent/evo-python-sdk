# evo-cli

LLM-first CLI for the [Seequent Evo](https://www.seequent.com/products-solutions/seequent-evo/) platform.

## Installation

```bash
pip install evo-cli
```

## Configuration

### Environment (QA vs production)

By default the CLI targets the **production** Evo environment. If you need to access the **QA** environment, set it first — before registering a client ID or logging in:

```bash
evo auth configure --env qa    # switch to QA
evo auth configure --env prod  # switch back to production (default)
```

Changing the environment clears any stored credentials, so you will need to re-run `evo auth configure --client-id` and `evo auth login` afterwards.

### App registration and client ID

Before using the CLI, register an Evo app and configure the CLI with its client ID.

```bash
# Prints a link to the app registration guide, and opens it in your browser.
evo auth configure

# Once you have a client ID:
evo auth configure --client-id <ID>
```

This is a one-time step per person (or per shared app, if your team registers one together).
Configuration is saved locally and used automatically by `evo auth login` from then on.

The CLI uses a default redirect URI (`http://localhost:3000/signin-callback`). If your
registered app needs a different one, set it explicitly:

```bash
evo auth configure --redirect-uri <URI>
```

To check your current configuration:

```bash
evo auth configure --show
```

To clear your configuration and start over (also logs you out):

```bash
evo auth configure --reset
```

## Credentials storage

After a successful login, credentials (access token, selected organisation, and hub URL) are stored securely in the OS credential store:

- **macOS** — Keychain
- **Windows** — Windows Credential Manager

No credentials are written to disk in plain text.

## Usage

```bash
# Authenticate (opens browser, prompts for org/hub if multiple are available)
evo auth login

# Show current login state
evo auth status

# Remove stored credentials
evo auth logout
```

### Hub selection

During `evo auth login` the CLI calls the Evo Discovery API to list the organisations and hubs your account has access to. If there is only one option it is selected automatically. If there are multiple, you will be prompted to choose. The selected hub URL is saved alongside the token and used for all subsequent API calls.
