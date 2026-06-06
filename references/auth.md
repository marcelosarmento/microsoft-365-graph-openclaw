# Auth Reference

## Profiles / contexts

Use **profiles** to keep Microsoft Graph accounts separate. A profile owns its own tenant, client ID, scopes, and token cache.

Recommended names:

- `personal` — Microsoft personal account (`@outlook.com`, Hotmail, Microsoft 365 Family, personal OneDrive)
- `work` — primary work/school Microsoft Entra account
- `work-empresa1`, `work-empresa2`, etc. — additional work contexts when needed

Token files:

- No profile / `default`: `state/graph_auth.json` (backward-compatible with the original single-login flow)
- Named profile: `state/graph_auth.<profile>.json` (for example `state/graph_auth.personal.json`)

Profile names may contain letters, numbers, dot, underscore, and hyphen.

## Choosing a profile

Two equivalent patterns are supported:

1. **Per-command environment variable** (works with every script and is easiest in OpenClaw-style automation):
   ```bash
   GRAPH_PROFILE=work python3 scripts/mail_fetch.py --folder Inbox --top 10
   GRAPH_PROFILE=personal python3 scripts/drive_ops.py list --path /
   ```
2. **CLI flag**:
   - Auth commands accept `--profile` after the auth subcommand:
     ```bash
     python3 scripts/graph_auth.py status --profile work
     ```
   - Scripts with subcommands accept `--profile` before the subcommand:
     ```bash
     python3 scripts/calendar_sync.py --profile work list --top 20
     ```
   - Single-command scripts accept `--profile` anywhere in their options:
     ```bash
     python3 scripts/mail_fetch.py --profile personal --folder Inbox --top 10
     ```

If neither `GRAPH_PROFILE` nor `--profile` is provided, scripts use `default` and keep the existing `state/graph_auth.json` behavior.

## Main path: use the Alitar app

You do not need to create an App Registration to get started. The skill uses **Openclaw Graph Integration by Alitar.one** by default (Client ID: `952d1b34-682e-48ce-9c54-bac5a96cbd42`). Run device login and grant consent for each profile you want to use.

- **Personal account (Outlook, Hotmail):** `--tenant-id consumers`
- **Work/school account (Entra ID):** `--tenant-id organizations` (or the tenant GUID)

## Recommended authentication profiles

### Personal Microsoft account (`@outlook.com`, `@hotmail.com`, Microsoft 365 Family)

```bash
python3 scripts/graph_auth.py device-login \
  --profile personal \
  --client-id 952d1b34-682e-48ce-9c54-bac5a96cbd42 \
  --tenant-id consumers
```

- **Use when**: you authenticate with Microsoft personal accounts (MSA), without corporate Entra ID.
- **Token file**: `state/graph_auth.personal.json`

### Work/school account (Microsoft Entra ID / Azure AD)

```bash
python3 scripts/graph_auth.py device-login \
  --profile work \
  --client-id 952d1b34-682e-48ce-9c54-bac5a96cbd42 \
  --tenant-id organizations
```

- **Use when**: you authenticate with a corporate or school account.
- **Token file**: `state/graph_auth.work.json`
- **Optional:** if your organization already has an approved App Registration, use `--client-id <your-app-id>` and `--tenant-id <tenant-id>`. See [Create Your Own App Registration](../docs/app-registration.md) for portal steps.

Suggested scopes for your own app:

- `Mail.ReadWrite`
- `Mail.Send`
- `Calendars.ReadWrite`
- `Files.ReadWrite.All`
- `Contacts.ReadWrite` *(remove if contacts are not needed)*
- `offline_access` (required for refresh token)

## Assisted device-code flow

1. Run device login for the target profile (examples above).
2. The script prints **URL** and **code**.
3. Open `https://microsoft.com/devicelogin`, paste the code, and authorize with the account that belongs to that profile.
4. On success, the script saves the profile-specific token state.
5. Tokens auto-refresh before requests. To force refresh:
   ```bash
   python3 scripts/graph_auth.py refresh --profile work
   ```
6. Scopes are fixed by the skill defaults; scope override via CLI is intentionally disabled.

## Status, refresh, and clear

```bash
python3 scripts/graph_auth.py status --profile personal
python3 scripts/graph_auth.py refresh --profile personal
python3 scripts/graph_auth.py clear --profile personal
```

Repeat with `--profile work` or another profile name for each context.

## Auth state structure

Named profile example (`state/graph_auth.work.json`):

```json
{
  "profile": "work",
  "client_id": "952d1b34-682e-48ce-9c54-bac5a96cbd42",
  "tenant_id": "organizations",
  "scopes": ["Mail.ReadWrite", "Mail.Send", "..."],
  "token": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": 1234567890
  }
}
```

Never commit `state/graph_auth.json`, `state/graph_auth.<profile>.json`, or token-bearing logs.

## Common errors

| Symptom | Fix |
| --- | --- |
| Operation uses the wrong account | Pass `--profile <name>` or prefix the command with `GRAPH_PROFILE=<name>`. |
| `No token available for profile ...` | Run device login for that exact profile. |
| `authorization_pending` | Wait; user has not completed authorization yet. |
| `interaction_required` | Re-run device login for the selected profile (token invalid/consent removed). |
| `AADSTS50059` on `/devicecode` | Tenant is incompatible with account type. For personal accounts use `--tenant-id consumers`. |
| `AADSTS700016` on `consumers` | `client_id` is not valid for Microsoft personal accounts. Use an MSA-compatible app registration. |
| `AADSTS70011 invalid_scope` with `OnlineMeetings.*` on `consumers` | `OnlineMeetings.*` scopes are not supported in this workflow for personal accounts. Remove these scopes and keep default scopes. |
| Repeated 401 errors | Run `graph_auth.py refresh --profile <name>`; if still failing, run `clear` and re-authenticate that profile. |
| 403 (Access Denied) | Add the required scope and grant consent again for the selected profile. |
