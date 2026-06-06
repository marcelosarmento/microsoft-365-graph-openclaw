---
name: microsoft-365-graph-openclaw
description: Microsoft 365 Graph for OpenClaw with focused daily Graph operations and optional webhook-based wake signals. Manage Outlook mail, calendar, OneDrive, and contacts via Microsoft Graph.
version: 0.2.2
license: MIT
homepage: https://github.com/draeden79/microsoft-365-graph-openclaw
repository: https://github.com/draeden79/microsoft-365-graph-openclaw
metadata: {"openclaw":{"homepage":"https://github.com/draeden79/microsoft-365-graph-openclaw","os":["linux","darwin","win32"],"requires":{"bins":["python3","bash","curl"]}}}
security:
  summary: OAuth-driven Microsoft Graph workflows with optional push-mode mail wake signals.
  notes:
    - Do not commit state/graph_auth.json, state/graph_ops.log, or token-bearing logs.
    - Keep hooks token and Graph clientState in protected env storage.
    - Prefer ordinary Graph scripts for daily work; use setup/infra scripts only when explicitly requested.
---

# Microsoft 365 Graph for OpenClaw Skill

This skill gives an agent operational access to Microsoft Graph for Outlook mail, calendar, OneDrive, and contacts. Keep the normal path simple: authenticate, check status/refresh, then run the workload script the user needs.

## Agent decision map

1. **Auth/status/token issue** → use `scripts/graph_auth.py`; details in [`references/auth.md`](references/auth.md).
2. **Read, filter, move, or send mail** → use `scripts/mail_fetch.py` or `scripts/mail_send.py`; details in [`references/mail.md`](references/mail.md).
3. **Calendar event work** → use `scripts/calendar_sync.py`; details in [`references/calendar.md`](references/calendar.md).
4. **OneDrive file work** → use `scripts/drive_ops.py`; details in [`references/drive.md`](references/drive.md).
5. **Contacts work** → use `scripts/contacts_ops.py`; details in [`references/contacts.md`](references/contacts.md).
6. **Already-configured push-mode status/renewal/queue health** → use [`references/mail_webhook_adapter.md`](references/mail_webhook_adapter.md).
7. **Setup, EC2, Caddy, systemd, OpenClaw hook config, smoke tests, or privileged troubleshooting** → use [`ops/mail-webhook.md`](ops/mail-webhook.md) only when explicitly asked for setup/infra.

## Daily prerequisites

- Run commands from the repository root.
- Python 3 and `requests` must be available.
- Tokens live in `state/graph_auth.json` for the backward-compatible `default` profile and `state/graph_auth.<profile>.json` for named profiles. All token files are ignored by git.
- Script activity is appended to `state/graph_ops.log`; do not commit logs.
- Default app values:
  - Client ID: `952d1b34-682e-48ce-9c54-bac5a96cbd42`
  - Personal-account tenant: `consumers`
  - Work/school tenant: `organizations` or tenant GUID
  - Default scopes: `Mail.ReadWrite Mail.Send Calendars.ReadWrite Files.ReadWrite.All Contacts.ReadWrite offline_access`

Permission profiles are in [`docs/permission-profiles.md`](docs/permission-profiles.md). App-registration setup is in [`docs/app-registration.md`](docs/app-registration.md).


## Profiles / account contexts

Use **profiles** when the same agent needs more than one Microsoft Graph account. A profile is a complete Graph context: client ID, tenant ID, default scopes, and token/cache path. Recommended names are `personal`, `work`, and specific names like `work-empresa1` for additional tenants.

- If no profile is provided, scripts use `default` and the existing `state/graph_auth.json` token cache. This preserves the original single-login workflow.
- Built-ins: `personal` and `work` are generic defaults. `personal` uses tenant `consumers`; `work` uses tenant `organizations`; both use default skill scopes and separate token files.
- To use your own `client_id`, tenant, or scopes for `personal`, `work`, or another profile, create `state/graph_profiles.json` (or set `GRAPH_PROFILES_FILE`) with `client_id`, `tenant_id`, `scopes`, and `auth_file`.
- For agents/OpenClaw, prefer per-command environment selection: `GRAPH_PROFILE=work python3 scripts/mail_fetch.py --folder Inbox --top 20`. It works the same way for every script and avoids confusion about `--profile` position.
- CLI selection is also supported. Auth commands use `--profile` after the auth subcommand; scripts with subcommands use `--profile` before the subcommand.

Authenticate each profile separately:

```bash
python3 scripts/graph_auth.py device-login --profile personal
python3 scripts/graph_auth.py device-login --profile work
```

Check the target profile before account-sensitive operations:

```bash
python3 scripts/graph_auth.py status --profile personal
python3 scripts/graph_auth.py status --profile work
```

See [`references/auth.md`](references/auth.md) for profile naming, token paths, and command syntax.

## Auth commands

Start device-code login for the target profile:

```bash
python3 scripts/graph_auth.py device-login --profile personal
```

For work/school accounts, use `--profile work`; the built-in `work` profile uses tenant `organizations`. Use `state/graph_profiles.json` or one-off login overrides only for custom tenants/apps.

Check and maintain auth state for the target profile:

```bash
python3 scripts/graph_auth.py status --profile personal
python3 scripts/graph_auth.py refresh --profile personal
python3 scripts/graph_auth.py clear --profile personal
```

Other Graph scripts call `utils.get_access_token()` and refresh tokens automatically when possible. Scope override is intentionally disabled; the skill uses `DEFAULT_SCOPES`.

## Common daily commands

### Mail

```bash
GRAPH_PROFILE=personal python3 scripts/mail_fetch.py --folder Inbox --top 20 --unread
GRAPH_PROFILE=work python3 scripts/mail_fetch.py --id "<messageId>" --include-body --mark-read
GRAPH_PROFILE=work python3 scripts/mail_fetch.py --id "<messageId>" --move-to "<folderId>"
GRAPH_PROFILE=work python3 scripts/mail_send.py --to user@example.com --subject "Update" --body-file replies/update.html --html
```

Use `--no-save-copy` only when the user intentionally does not want a Sent Items copy.

### Calendar

```bash
GRAPH_PROFILE=work python3 scripts/calendar_sync.py list --start 2026-03-03T00:00Z --end 2026-03-05T23:59Z --top 50
GRAPH_PROFILE=work python3 scripts/calendar_sync.py create --subject "Meeting" --start 2026-03-05T12:00 --end 2026-03-05T13:00 --tz UTC --attendees person@example.com
GRAPH_PROFILE=work python3 scripts/calendar_sync.py update "<eventId>" --start 2026-03-05T12:30 --end 2026-03-05T13:30
GRAPH_PROFILE=work python3 scripts/calendar_sync.py cancel "<eventId>" --message "Rescheduling this event."
```

For personal Microsoft accounts (`tenant=consumers`), Graph may not return a Teams join URL even when `--online` is used.

### OneDrive

```bash
GRAPH_PROFILE=personal python3 scripts/drive_ops.py list --path /
GRAPH_PROFILE=personal python3 scripts/drive_ops.py upload --local notes/briefing.docx --remote /Clients/briefing.docx
GRAPH_PROFILE=personal python3 scripts/drive_ops.py download --remote /Clients/briefing.docx --local /tmp/briefing.docx
GRAPH_PROFILE=personal python3 scripts/drive_ops.py share --remote /Clients/briefing.docx
```

The drive script resolves localized/special-folder aliases such as `Documents` and `Documentos`.

### Contacts

```bash
GRAPH_PROFILE=work python3 scripts/contacts_ops.py list --top 20
GRAPH_PROFILE=work python3 scripts/contacts_ops.py list --search "Jane"
GRAPH_PROFILE=work python3 scripts/contacts_ops.py create --given-name Jane --surname Doe --email jane.doe@example.com
GRAPH_PROFILE=work python3 scripts/contacts_ops.py update "<contactId>" --mobile "+1 555 0123"
GRAPH_PROFILE=work python3 scripts/contacts_ops.py delete "<contactId>"
```

## Push-mode boundary

Mail push mode is useful for production wake signals, but it is not the normal path for daily Graph tasks.

Only use push-mode files when the user explicitly asks for webhook/push behavior or the system is already configured and needs operational checks:

- Safe operational reference: [`references/mail_webhook_adapter.md`](references/mail_webhook_adapter.md)
- Setup/infra/runbook reference: [`ops/mail-webhook.md`](ops/mail-webhook.md)
- Human minimal setup: [`docs/minimal-setup.md`](docs/minimal-setup.md)
- OpenClaw hook setup: [`docs/setup-openclaw-hooks.md`](docs/setup-openclaw-hooks.md)
- Heavy troubleshooting: [`docs/troubleshooting.md`](docs/troubleshooting.md)

Privileged setup scripts are **not** daily commands:

- `scripts/setup_mail_webhook_ec2.sh`
- `scripts/run_mail_webhook_e2e_setup.sh`

When run without `--dry-run`, they can write `/etc/default/graph-mail-webhook`, Caddy config, and systemd units; enable/restart services; and optionally patch OpenClaw config. Run them only after explicit setup/infra intent and a `--dry-run` review.

## Troubleshooting quick table

| Symptom | First action |
| --- | --- |
| Auth status missing/expired | `python3 scripts/graph_auth.py status --profile <name>`, then `refresh` or device login for that profile. |
| `401` / `invalid_grant` | Refresh; if it still fails, clear and repeat device login. |
| `403` / `AccessDenied` | Confirm scopes/consent and account policy. |
| `429` / throttling | Wait and retry; scripts include basic retry behavior. |
| Operation hits the wrong account | Re-run with `GRAPH_PROFILE=<name>` or `--profile <name>`. |
| Push queue/log issue | Use [`references/mail_webhook_adapter.md`](references/mail_webhook_adapter.md), not setup scripts, unless setup was requested. |

This skill should keep daily agent work on the unprivileged Graph scripts and keep setup/infra material out of the main path.
