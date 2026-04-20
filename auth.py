"""OAuth token management for the Adobe Analytics MCP server.

Two auth paths — all configured via env vars in settings.json:

  OAuth (interactive, one-time setup):
    AW_CLIENT_ID, AW_CLIENT_SECRET, AW_COMPANY_ID
    1. get_auth_url() → user visits URL, logs in, copies code
    2. exchange_code(code) → stores tokens in .tokens.json; auto-refreshes forever

  OAuth (pre-seeded, no browser needed):
    AW_CLIENT_ID, AW_CLIENT_SECRET, AW_COMPANY_ID, AW_REFRESH_TOKEN
    get_valid_token() bootstraps from AW_REFRESH_TOKEN on first call.

S2S auth is handled entirely by the R layer (adobeanalyticsr::aw_auth_with/aw_auth).
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".tokens.json")
_REDIRECT_URI = "https://adobeanalyticsr.com/token_result.html"
_AUTHORIZE_URL = "https://ims-na1.adobelogin.com/ims/authorize/v2"
_TOKEN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
_SCOPE = "openid,AdobeID,read_organizations,additional_info.projectedProductContext"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_auth_url() -> str:
    """Return the Adobe OAuth authorization URL for the user to visit."""
    client_id = _require_env("AW_CLIENT_ID")
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "scope": _SCOPE,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
    })
    return f"{_AUTHORIZE_URL}?{params}"


def exchange_code(code: str) -> dict:
    """Exchange an authorization code for tokens and persist them.

    Args:
        code: The authorization code from the OAuth redirect page.

    Returns:
        dict with access_token, refresh_token, and expires_at (Unix timestamp).
    """
    client_id = _require_env("AW_CLIENT_ID")
    client_secret = _require_env("AW_CLIENT_SECRET")

    tokens = _post_token_request({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": _REDIRECT_URI,
    })
    _save_tokens(tokens)
    return tokens


def get_valid_token() -> str:
    """Return a valid OAuth access token, refreshing silently if needed.

    If no .tokens.json exists but AW_REFRESH_TOKEN is set in the environment,
    bootstraps automatically without any browser interaction.

    Raises:
        RuntimeError: if not authenticated or refresh fails.
    """
    tokens = _load_tokens()

    if not tokens:
        env_refresh = os.environ.get("AW_REFRESH_TOKEN", "")
        if env_refresh:
            tokens = _refresh(env_refresh)
        else:
            raise RuntimeError(
                "Not authenticated. Use get_auth_url() to get a login link, "
                "then complete_auth() with the code shown after you log in. "
                "Alternatively, set AW_REFRESH_TOKEN in your settings.json env."
            )

    # Refresh 5 minutes before expiry to avoid clock-skew issues
    if time.time() > tokens["expires_at"] - 300:
        refresh = tokens.get("refresh_token") or os.environ.get("AW_REFRESH_TOKEN", "")
        if not refresh:
            raise RuntimeError(
                "Access token expired and no refresh token is available. "
                "Re-authenticate via get_auth_url() or set AW_REFRESH_TOKEN."
            )
        tokens = _refresh(refresh)

    return tokens["access_token"]


def auth_status() -> dict:
    """Return current authentication status."""
    tokens = _load_tokens()
    if not tokens:
        return {"authenticated": False}
    expires_in = int(tokens["expires_at"] - time.time())
    return {
        "authenticated": True,
        "expires_in_seconds": max(expires_in, 0),
        "token_valid": expires_in > 0,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} environment variable is not set")
    return value


def _post_token_request(params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(_TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Token exchange failed ({e.code}): {body}") from e
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": time.time() + result.get("expires_in", 3600),
    }


def _refresh(refresh_token: str) -> dict:
    client_id = _require_env("AW_CLIENT_ID")
    client_secret = _require_env("AW_CLIENT_SECRET")
    tokens = _post_token_request({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })
    # Adobe may or may not return a new refresh token; keep the old one if not
    if not tokens["refresh_token"]:
        tokens["refresh_token"] = refresh_token
    _save_tokens(tokens)
    return tokens


def _save_tokens(tokens: dict) -> None:
    with open(_TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(_TOKEN_FILE, 0o600)


def _load_tokens() -> dict | None:
    if not os.path.exists(_TOKEN_FILE):
        return None
    with open(_TOKEN_FILE) as f:
        return json.load(f)
