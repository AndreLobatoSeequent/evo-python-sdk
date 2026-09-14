# evo-cli

LLM-first CLI for the [Seequent Evo](https://www.seequent.com/products-solutions/seequent-evo/) platform.

## Installation

```bash
pip install evo-cli
```

## App Registration

Before using the CLI, register a native application in the [Bentley Developer Portal](https://developer.bentley.com/):

1. Create a new **Native / SPA** application
2. Add the required Evo API scopes: `evo.discovery`, `evo.workspace` (and others as needed)
3. Add your redirect URI (e.g. `http://localhost:8888/callback`) to the allowed redirect URIs list

## Configuration

Set the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `EVO_CLIENT_ID` | Yes | Client ID from your Bentley Developer Portal app registration |
| `EVO_REDIRECT_URI` | Yes | Redirect URI registered in your app (e.g. `http://localhost:8888/callback`) |
| `EVO_ENV` | No | Target environment: `prod` (default) or `qa` |
| `EVO_IMS_URL` | No | Override the IMS (auth) URL — takes precedence over `EVO_ENV` |
| `EVO_DISCOVERY_URL` | No | Override the Discovery API URL — takes precedence over `EVO_ENV` |

### Environment presets

`EVO_ENV` selects a matched pair of IMS and Discovery URLs:

| `EVO_ENV` | IMS URL | Discovery URL |
|-----------|---------|---------------|
| `prod` (default) | `https://ims.bentley.com` | `https://discover.api.seequent.com` |
| `qa` | `https://qa-ims.bentley.com` | `https://discover.dev.evo.seequent.dev` |

`EVO_IMS_URL` and `EVO_DISCOVERY_URL` can override individual URLs from the preset when needed (e.g. pointing at a local dev service).

### Example: production

```bash
export EVO_CLIENT_ID="your-client-id"
export EVO_REDIRECT_URI="http://localhost:8888/callback"
```

### Example: QA / development

```bash
export EVO_CLIENT_ID="your-qa-client-id"
export EVO_REDIRECT_URI="http://localhost:8888/callback"
export EVO_ENV=qa
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
