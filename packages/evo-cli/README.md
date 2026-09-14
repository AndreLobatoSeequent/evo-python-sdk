# evo-cli

LLM-first CLI for the [Seequent Evo](https://www.seequent.com/products-solutions/seequent-evo/) platform.

## Installation

```bash
pip install evo-cli
```

## Configuration

Register an application in the [Bentley Developer Portal](https://developer.bentley.com/) and set:

```bash
export EVO_CLIENT_ID="your-client-id"
export EVO_REDIRECT_URI="http://localhost:8888/callback"
```

## Usage

```bash
evo auth login    # open browser, select org, save credentials
evo auth status   # show current login state
evo auth logout   # remove stored credentials
```
