import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = WORKSPACE_ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)
AUTH_FILE = STATE_DIR / "graph_auth.json"
LOG_FILE = STATE_DIR / "graph_ops.log"
_profile_config_file_raw = Path(os.getenv("GRAPH_PROFILES_FILE", str(STATE_DIR / "graph_profiles.json"))).expanduser()
PROFILE_CONFIG_FILE = _profile_config_file_raw if _profile_config_file_raw.is_absolute() else WORKSPACE_ROOT / _profile_config_file_raw
DEFAULT_PROFILE = os.getenv("GRAPH_PROFILE", "default")
PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# Default app/tenant tuned for Microsoft personal accounts.
# Override with GRAPH_CLIENT_ID / GRAPH_TENANT_ID or CLI args when needed.
DEFAULT_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "952d1b34-682e-48ce-9c54-bac5a96cbd42")
DEFAULT_TENANT = os.getenv("GRAPH_TENANT_ID", "consumers")
DEFAULT_SCOPES = [
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Files.ReadWrite.All",
    "Contacts.ReadWrite",
    "offline_access",
]
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_SAFETY_MARGIN = 120  # seconds
_ACTIVE_PROFILE = DEFAULT_PROFILE


def normalize_profile(profile: Optional[str] = None) -> str:
    name = (profile or DEFAULT_PROFILE or "default").strip()
    if not name:
        name = "default"
    if not PROFILE_NAME_RE.fullmatch(name):
        raise ValueError("Profile names may contain only letters, numbers, dot, underscore, and hyphen.")
    return name


def _default_auth_file_for_profile(profile: Optional[str] = None) -> Path:
    name = normalize_profile(profile)
    if name == "default":
        return AUTH_FILE
    return STATE_DIR / f"graph_auth.{name}.json"


def _resolve_profile_path(value: Optional[str], fallback: Path) -> Path:
    if not value:
        return fallback
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    return path


def _builtin_profile_config(profile: str) -> Dict[str, Any]:
    tenant = "organizations" if profile == "work" else DEFAULT_TENANT
    if profile == "personal":
        tenant = "consumers"
    return {
        "profile": profile,
        "client_id": DEFAULT_CLIENT_ID,
        "tenant_id": tenant,
        "scopes": list(DEFAULT_SCOPES),
        "auth_file": str(_default_auth_file_for_profile(profile)),
    }


def load_profiles_config() -> Dict[str, Any]:
    if not PROFILE_CONFIG_FILE.exists():
        return {"profiles": {}}
    with PROFILE_CONFIG_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Profile config must be a JSON object: {PROFILE_CONFIG_FILE}")
    profiles = data.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError(f"Profile config 'profiles' must be an object: {PROFILE_CONFIG_FILE}")
    return data


def get_profile_config(profile: Optional[str] = None) -> Dict[str, Any]:
    name = normalize_profile(profile) if profile is not None else get_active_profile()
    config = _builtin_profile_config(name)
    profiles = load_profiles_config().get("profiles", {})
    raw = profiles.get(name, {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"Profile config for {name!r} must be an object.")
    config.update({k: v for k, v in raw.items() if v is not None})
    config["profile"] = name
    config["client_id"] = config.get("client_id") or DEFAULT_CLIENT_ID
    config["tenant_id"] = config.get("tenant_id") or DEFAULT_TENANT
    scopes = config.get("scopes") or DEFAULT_SCOPES
    if isinstance(scopes, str):
        scopes = scopes.split()
    config["scopes"] = list(scopes)
    auth_value = config.get("auth_file") or config.get("token_path")
    config["auth_file"] = str(_resolve_profile_path(auth_value, _default_auth_file_for_profile(name)))
    return config


def auth_file_for_profile(profile: Optional[str] = None) -> Path:
    return Path(get_profile_config(profile).get("auth_file", _default_auth_file_for_profile(profile)))


def set_active_profile(profile: Optional[str] = None) -> str:
    global _ACTIVE_PROFILE
    _ACTIVE_PROFILE = normalize_profile(profile)
    return _ACTIVE_PROFILE


def get_active_profile() -> str:
    return normalize_profile(_ACTIVE_PROFILE)


def add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Graph auth profile/context to use (default: GRAPH_PROFILE or 'default').",
    )


def configure_profile_from_args(args: argparse.Namespace) -> str:
    return set_active_profile(getattr(args, "profile", None))


def load_auth_state(profile: Optional[str] = None) -> Dict[str, Any]:
    name = normalize_profile(profile) if profile is not None else get_active_profile()
    auth_file = auth_file_for_profile(name)
    if auth_file.exists():
        with auth_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("profile", name)
            return data
    return {}


def save_auth_state(data: Dict[str, Any], profile: Optional[str] = None) -> None:
    if profile is not None:
        name = normalize_profile(profile)
    elif data.get("profile"):
        name = normalize_profile(data.get("profile"))
    else:
        name = get_active_profile()
    data["profile"] = name
    auth_file = auth_file_for_profile(name)
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    with auth_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def append_log(entry: Dict[str, Any]) -> None:
    entry.setdefault("timestamp", int(time.time()))
    entry.setdefault("profile", get_active_profile())
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _authority(tenant_id: Optional[str] = None) -> str:
    tenant = tenant_id or DEFAULT_TENANT
    return f"https://login.microsoftonline.com/{tenant}"


def token_expired(token: Dict[str, Any]) -> bool:
    expires_at = token.get("expires_at")
    if not expires_at:
        return True
    return time.time() > (expires_at - TOKEN_SAFETY_MARGIN)


def _request_token(data: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict[str, Any]:
    authority = _authority(tenant_id)
    resp = requests.post(f"{authority}/oauth2/v2.0/token", data=data, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    expires_in = int(payload.get("expires_in", 3600))
    payload["expires_at"] = int(time.time()) + expires_in
    return payload


def refresh_access_token(force: bool = False, profile: Optional[str] = None) -> Dict[str, Any]:
    name = normalize_profile(profile) if profile is not None else get_active_profile()
    state = load_auth_state(name)
    token = state.get("token")
    if not token:
        raise RuntimeError(f"No token available for profile '{name}'. Run graph_auth.py device-login first.")
    if not force and not token_expired(token):
        return token
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(f"Refresh token missing for profile '{name}'. Re-run device login.")
    config = get_profile_config(name)
    client_id = state.get("client_id", config["client_id"])
    tenant_id = state.get("tenant_id", config["tenant_id"])
    scope_str = " ".join(state.get("scopes", config["scopes"]))
    new_token = _request_token(
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": scope_str,
        },
        tenant_id,
    )
    state["token"] = new_token
    save_auth_state(state, name)
    return new_token


def get_access_token(profile: Optional[str] = None) -> str:
    name = normalize_profile(profile) if profile is not None else get_active_profile()
    state = load_auth_state(name)
    token = state.get("token")
    if not token or token_expired(token):
        token = refresh_access_token(force=True, profile=name)
    return token["access_token"]


def authorized_request(method: str, url: str, **kwargs) -> requests.Response:
    profile = kwargs.pop("profile", None)
    name = normalize_profile(profile) if profile is not None else get_active_profile()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {get_access_token(name)}"
    headers.setdefault("Accept", "application/json")
    if "json" in kwargs and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
    kwargs["headers"] = headers
    resp = requests.request(method, url, timeout=60, **kwargs)
    if resp.status_code == 401:
        # token might be expired; refresh once
        refresh_access_token(force=True, profile=name)
        headers["Authorization"] = f"Bearer {get_access_token(name)}"
        resp = requests.request(method, url, timeout=60, **kwargs)
    resp.raise_for_status()
    return resp


def graph_url(path: str) -> str:
    if path.startswith("http"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return GRAPH_BASE_URL + path


def chunk_iterable(values: Iterable[str], size: int = 10) -> Iterable[list]:
    bucket = []
    for value in values:
        bucket.append(value)
        if len(bucket) == size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


def encode_attachment(path: Path) -> Dict[str, Any]:
    data = path.read_bytes()
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": path.name,
        "contentBytes": base64.b64encode(data).decode("utf-8"),
    }


def parse_recipients(addresses: Iterable[str]) -> Iterable[Dict[str, Dict[str, str]]]:
    for addr in addresses:
        addr = addr.strip()
        if not addr:
            continue
        yield {"emailAddress": {"address": addr}}


def cli_main(handler):
    try:
        handler()
    except requests.HTTPError as exc:
        print(f"Graph API error: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
