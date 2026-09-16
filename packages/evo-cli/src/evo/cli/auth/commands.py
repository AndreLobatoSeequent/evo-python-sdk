#  Copyright © 2025 Bentley Systems, Incorporated
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#      http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import annotations

import asyncio
import webbrowser
from typing import TYPE_CHECKING

import typer

from evo.cli import output, useragent
from evo.cli.config import CliConfig, get_client_id, get_environment, get_redirect_uri, load_config, save_config
from evo.cli.state import CurrentSelection, load_selection, save_selection
from evo.oauth import AuthorizationCodeAuthorizer
from evo.oauth.data import EvoScopes, Scopes

from .token_store import StoredCredentials, delete_credentials, load_credentials, save_credentials

if TYPE_CHECKING:
    # Only used in type annotations below; `from __future__ import annotations` makes these lazy
    # strings, so importing evo.oauth.data.AccessToken for real is unnecessary at import time.
    from evo.oauth.data import AccessToken

app = typer.Typer(help="Authenticate with Seequent Evo.")

_CLI_SCOPES: Scopes = (
    EvoScopes.all_evo  # evo.discovery | evo.workspace | evo.blocksync | evo.object | evo.file
    | EvoScopes.evo_audit
    | EvoScopes.offline_access  # required for refresh tokens
    | "itwin-platform"
    | "evo.users:read"
    | "evo.lineage:read"
)


class _CapturingAuthorizer(AuthorizationCodeAuthorizer):
    """Subclass that exposes the token after login so it can be persisted."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._captured_token: AccessToken | None = None

    def _update_token(self, new_token: AccessToken) -> None:
        self._captured_token = new_token
        super()._update_token(new_token)


_GUIDANCE_TEMPLATE = """\
Evo apps provide the credentials necessary to generate Evo access tokens, which in turn
provide access to your Evo data. An app can be created by you or by a member of your team.

For instructions on registering an Evo app, see the guide:
  {guide_url}

Once you have a client ID, run:
  evo auth configure --client-id <ID>"""


def _build_configure_epilog() -> str:
    guide_url = get_environment().docs_url
    return (
        "Evo apps provide the credentials necessary to generate Evo access tokens, which in "
        "turn provide access to your Evo data. An app can be created by you or by a member of "
        f"your team. For instructions on registering one, see the guide: {guide_url}"
    )


async def _do_login() -> None:
    from evo.aio.transport import AioTransport
    from evo.common import APIConnector
    from evo.discovery import DiscoveryAPIClient
    from evo.oauth import OAuthConnector

    existing = load_credentials()
    if existing is not None and not existing.token.is_expired:
        output.emit(
            {"org_name": existing.org_name, "hub_url": existing.hub_url, "status": "already_logged_in"},
            plain=f"Already logged in — Org: {existing.org_name}, Hub: {existing.hub_url}",
        )
        return

    client_id = get_client_id()
    if not client_id:
        output.emit_error(
            "Evo client ID is not configured. Run 'evo auth configure' to get started.",
            hint="evo auth configure",
        )

    redirect_uri = get_redirect_uri()

    try:
        env = get_environment()
    except ValueError as e:
        output.emit_error(str(e))

    transport = AioTransport(user_agent=useragent.get_user_agent())

    oauth_connector = OAuthConnector(transport, client_id=client_id, base_uri=env.ims_url)
    authorizer = _CapturingAuthorizer(oauth_connector=oauth_connector, redirect_url=redirect_uri, scopes=_CLI_SCOPES)

    if output.is_interactive():
        typer.echo(f"Opening browser for authentication… (env: {env.name})")
    await authorizer.login(timeout_seconds=180)

    if authorizer._captured_token is None:
        output.emit_error("authentication did not produce a token")

    token = authorizer._captured_token

    async with APIConnector(env.discovery_url, transport, authorizer) as connector:
        discovery = DiscoveryAPIClient(connector)
        orgs = await discovery.list_organizations(service_codes=["evo"])

    # Imported lazily to avoid a circular import: _session imports from evo.cli.auth.token_store,
    # which (as a submodule of this package) forces auth/__init__.py - and therefore this module -
    # to load first.
    from .._session import select_org_and_hub as _select_org_and_hub

    org, hub = _select_org_and_hub(orgs)

    creds = StoredCredentials(
        token=token,
        org_id=org.id,
        org_name=org.display_name,
        hub_url=hub.url,
        hub_code=hub.code,
        client_id=client_id,
        ims_url=env.ims_url,
    )
    save_credentials(creds)

    existing = load_selection()
    same_hub = existing.hub_code == hub.code and existing.org_id == org.id
    save_selection(
        CurrentSelection(
            org_id=org.id,
            org_name=org.display_name,
            hub_code=hub.code,
            hub_url=hub.url,
            hub_display_name=hub.display_name,
            # carry workspace forward when re-logging into the same org/hub
            workspace_id=existing.workspace_id if same_hub else None,
            workspace_name=existing.workspace_name if same_hub else None,
        )
    )

    output.emit(
        {"org_name": org.display_name, "hub_url": hub.url, "status": "logged_in"},
        plain=f"Logged in — Org: {org.display_name}, Hub: {hub.url}",
    )


async def _do_status() -> None:
    creds = load_credentials()
    if creds is None:
        output.emit(
            {"status": "not_logged_in"},
            plain="Not logged in. Run 'evo auth login' to authenticate.",
        )
        return
    if creds.token.is_expired:
        output.emit(
            {"status": "expired"},
            plain="Session expired. Run 'evo auth login' to re-authenticate.",
        )
        return
    expires_at = creds.token.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    output.emit(
        {"status": "logged_in", "org_name": creds.org_name, "hub_url": creds.hub_url, "expires_at": expires_at},
        plain=f"Logged in — Org: {creds.org_name}, Hub: {creds.hub_url}, Token expires: {expires_at}",
    )


@app.command()
def login() -> None:
    """Authenticate with Seequent Evo (opens browser)."""
    asyncio.run(_do_login())


@app.command()
def logout() -> None:
    """Remove stored credentials."""
    delete_credentials()
    output.emit({"status": "logged_out"}, plain="Logged out.")


@app.command()
def status() -> None:
    """Show current authentication state."""
    asyncio.run(_do_status())


def _emit_current_config(config, *, hint: bool) -> None:
    plain = (
        f"Client ID: {config.client_id or '(not set)'}\nRedirect URI: {config.redirect_uri}\nEnvironment: {config.env}"
    )
    if hint:
        plain += "\n\nTo change this, run 'evo auth configure --client-id <ID>' (see --help for details)."
    output.emit(
        {"client_id": config.client_id, "redirect_uri": config.redirect_uri, "env": config.env},
        plain=plain,
    )


@app.command(epilog=_build_configure_epilog())
def configure(
    client_id: str | None = typer.Option(None, "--client-id", help="Client ID from your registered Evo app."),
    redirect_uri: str | None = typer.Option(None, "--redirect-uri", help="Redirect URI registered for your app."),
    env: str | None = typer.Option(None, "--env", help="Evo environment to use (prod or qa)."),
    show: bool = typer.Option(False, "--show", help="Show the current configuration."),
    reset: bool = typer.Option(False, "--reset", help="Clear all configuration and return to defaults."),
) -> None:
    """Set up the Evo CLI: register your app's client ID and (optionally) its redirect URI."""
    config = load_config()

    if reset:
        if client_id is not None or redirect_uri is not None or env is not None or show:
            output.emit_error("--reset cannot be combined with other options.")
        defaults = CliConfig()
        save_config(defaults)
        delete_credentials()
        output.emit(
            {
                "status": "reset",
                "client_id": defaults.client_id,
                "redirect_uri": defaults.redirect_uri,
                "env": defaults.env,
            },
            plain=f"Configuration reset to defaults. Redirect URI: {defaults.redirect_uri}, "
            f"Environment: {defaults.env}. You have been logged out.",
        )
        return

    if show:
        _emit_current_config(config, hint=False)
        return

    if client_id is None and redirect_uri is None and env is None:
        if config.client_id is not None:
            _emit_current_config(config, hint=True)
            return

        current_env = get_environment()
        message = _GUIDANCE_TEMPLATE.format(guide_url=current_env.docs_url)
        if output.is_interactive():
            try:
                webbrowser.open(current_env.docs_url)
            except Exception:
                pass
        output.emit(
            {"status": "setup_required", "guide_url": current_env.docs_url},
            plain=message,
        )
        return

    env_changed = False
    if env is not None:
        try:
            resolved = get_environment(env)
        except ValueError as e:
            output.emit_error(str(e))
        env_changed = resolved.name != config.env
        config.env = resolved.name

    if client_id is not None:
        config.client_id = client_id
    if redirect_uri is not None:
        config.redirect_uri = redirect_uri

    save_config(config)

    if env_changed:
        delete_credentials()

    lines = ["Configuration updated."]
    if client_id is not None:
        lines.append(f"Client ID: {config.client_id}")
    if redirect_uri is not None:
        lines.append(f"Redirect URI: {config.redirect_uri}")
    if env is not None:
        lines.append(f"Environment: {config.env}")

    next_step = None
    if env_changed:
        next_step = "evo auth login"
        lines.append("Environment changed — you have been logged out. Run 'evo auth login' to re-authenticate.")
    elif client_id is not None:
        next_step = "evo auth login"
        lines.append("Run 'evo auth login' to authenticate.")

    output.emit(
        {
            "status": "updated",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "env": config.env,
            "env_changed": env_changed,
            "next_step": next_step,
        },
        plain="\n".join(lines),
    )
