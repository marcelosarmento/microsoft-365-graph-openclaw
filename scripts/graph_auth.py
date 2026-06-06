#!/usr/bin/env python3
"""Device code + refresh token management for Microsoft Graph."""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

import requests

sys.path.append(str(Path(__file__).resolve().parent))
from utils import (  # noqa: E402
    PROFILE_CONFIG_FILE,
    add_profile_argument,
    append_log,
    auth_file_for_profile,
    configure_profile_from_args,
    get_profile_config,
    load_auth_state,
    save_auth_state,
    token_expired,
    TOKEN_SAFETY_MARGIN,
    _authority,
    _request_token,
)

CORE_SKILL_SCOPES = {
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Files.ReadWrite.All",
    "Contacts.ReadWrite",
    "offline_access",
}


def warn_if_missing_core_scopes(scopes: List[str], context: str) -> None:
    missing = sorted(CORE_SKILL_SCOPES.difference(set(scopes)))
    if not missing:
        return
    joined = ", ".join(missing)
    print(
        f"[warning] Missing scopes for full skill usage ({context}): {joined}.",
        file=sys.stderr,
    )
    print(
        "[warning] Re-authenticate with the default email + calendar scopes.",
        file=sys.stderr,
    )


def validate_scope_tenant_compatibility(scopes: List[str], tenant_id: str) -> None:
    has_online_meetings_scope = any(scope.startswith("OnlineMeetings.") for scope in scopes)
    if has_online_meetings_scope and tenant_id.lower() == "consumers":
        raise ValueError(
            "OnlineMeetings.* scopes are not supported for tenant=consumers in this workflow. "
            "Remove OnlineMeetings scopes for personal accounts."
        )


def request_device_code(client_id: str, scopes: List[str], tenant_id: str) -> dict:
    authority = _authority(tenant_id)
    resp = requests.post(
        f"{authority}/oauth2/v2.0/devicecode",
        data={"client_id": client_id, "scope": " ".join(scopes)},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def poll_for_token(device_data: dict, client_id: str, tenant_id: str) -> dict:
    interval = int(device_data.get("interval", 5))
    expires_in = int(device_data.get("expires_in", 900))
    deadline = time.time() + expires_in
    print("Waiting for authorization...", flush=True)
    while time.time() < deadline:
        time.sleep(interval)
        try:
            return _request_token(
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id,
                    "device_code": device_data["device_code"],
                },
                tenant_id,
            )
        except requests.HTTPError as exc:
            error = exc.response.json()
            if error.get("error") in {"authorization_pending", "slow_down"}:
                if error.get("error") == "slow_down":
                    interval += 2
                continue
            raise
    raise TimeoutError("Device code expired before authorization completed.")


def command_device_login(args: argparse.Namespace) -> None:
    profile = configure_profile_from_args(args)
    config = get_profile_config(profile)
    scopes = list(config["scopes"])
    client_id = args.client_id or config["client_id"]
    tenant_id = args.tenant_id or config["tenant_id"]
    validate_scope_tenant_compatibility(scopes, tenant_id)
    warn_if_missing_core_scopes(scopes, "device-login")
    device = request_device_code(client_id, scopes, tenant_id)
    verification_uri = device.get("verification_uri") or device.get("verification_uri_complete")
    print("=== Authorize access ===")
    print(f"URL: {verification_uri}")
    print(f"Code: {device['user_code']}")
    print("Enter the code above and continue with your target account.")
    token = poll_for_token(device, client_id, tenant_id)
    state = {
        "client_id": client_id,
        "tenant_id": tenant_id,
        "scopes": scopes,
        "token": token,
        "auth_file": str(auth_file_for_profile(profile)),
    }
    save_auth_state(state, profile)
    append_log({"action": "auth_login", "tenant": tenant_id, "scopes": scopes})
    print(f"Authorization successful for profile {profile!r}. Tokens saved to {auth_file_for_profile(profile)}")


def command_refresh(args: argparse.Namespace) -> None:
    profile = configure_profile_from_args(args)
    state = load_auth_state(profile)
    if not state.get("token"):
        raise RuntimeError("No token found. Run device-login first.")
    config = get_profile_config(profile)
    token = _request_token(
        {
            "client_id": state.get("client_id", config["client_id"]),
            "grant_type": "refresh_token",
            "refresh_token": state["token"].get("refresh_token"),
            "scope": " ".join(state.get("scopes", config["scopes"])),
        },
        state.get("tenant_id", config["tenant_id"]),
    )
    state["token"] = token
    save_auth_state(state, profile)
    append_log({"action": "auth_refresh"})
    print(f"Token refreshed for profile {profile!r}.")


def command_status(args: argparse.Namespace) -> None:
    profile = configure_profile_from_args(args)
    state = load_auth_state(profile)
    config = get_profile_config(profile)
    if not state:
        print(f"No saved auth state for profile {profile!r} at {auth_file_for_profile(profile)}.")
        print("Profile config:")
        print(json.dumps({k: config[k] for k in ["profile", "client_id", "tenant_id", "scopes", "auth_file"]}, indent=2))
        print(f"Config source: {PROFILE_CONFIG_FILE} (if present) plus built-in defaults.")
        return
    token = state.get("token")
    scopes = state.get("scopes", [])
    warn_if_missing_core_scopes(scopes, "saved state")
    expires = token.get("expires_at") if token else None
    seconds = int(expires - time.time()) if expires else None
    print(json_summary(state))
    if seconds is not None:
        print(f"Expires in {seconds} seconds (safety margin: {TOKEN_SAFETY_MARGIN}s).")
        print("Expired?", token_expired(token))


def command_clear(args: argparse.Namespace) -> None:
    profile = configure_profile_from_args(args)
    auth_file = auth_file_for_profile(profile)
    if auth_file.exists():
        auth_file.unlink()
    append_log({"action": "auth_clear"})
    print(f"Authentication state removed for profile {profile!r}.")


def json_summary(state: dict) -> str:
    safe = {**state}
    token = safe.get("token")
    if token:
        safe["token"] = {
            k: v
            for k, v in token.items()
            if k in {"expires_at", "expires_in", "token_type"}
        }
    return json.dumps(safe, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage OAuth device-code authentication for Microsoft Graph.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("device-login", help="Start device-code sign-in flow.")
    p_login.add_argument("--client-id", help="Override profile Client ID for this login.")
    p_login.add_argument("--tenant-id", help="Override profile tenant (consumers, organizations, common, or GUID) for this login.")
    add_profile_argument(p_login)

    p_refresh = sub.add_parser("refresh", help="Force immediate token refresh.")
    add_profile_argument(p_refresh)
    p_status = sub.add_parser("status", help="Show current auth/token status.")
    add_profile_argument(p_status)
    p_clear = sub.add_parser("clear", help="Delete saved token state.")
    add_profile_argument(p_clear)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command
    if command == "device-login":
        command_device_login(args)
    elif command == "refresh":
        command_refresh(args)
    elif command == "status":
        command_status(args)
    elif command == "clear":
        command_clear(args)
    else:
        parser.error("Unknown command")


if __name__ == "__main__":
    main()
