# Auth Reference

## Main path: Tuco personal Microsoft account

The personal-first baseline uses Tuco's own App Registration in the Stridesense tenant.

- **Client ID:** `e8ee2c58-635e-491f-99f7-c60b63b70f64`
- **Tenant:** `consumers`
- **Default scopes:** `User.Read Files.Read offline_access`
- **Token cache:** `~/.openclaw/graph/personal-token.json`

The App Registration must:
- Support **Personal Microsoft accounts only** or another mode that includes personal Microsoft accounts.
- Be configured as a public client for device-code flow.
- Use conservative delegated permissions first; expand scopes only per module.

## Recommended authentication profiles

### Personal Microsoft account (`@outlook.com`, `@hotmail.com`, Microsoft 365 Family)

- **Skill default Client ID**: `e8ee2c58-635e-491f-99f7-c60b63b70f64`
- **Skill default tenant**: `consumers`
- **Use when**: you authenticate with Microsoft personal accounts (MSA), without corporate Entra ID.
- **Initial scope**: OneDrive read-only baseline (`Files.Read`) plus `User.Read` and `offline_access`.

### Work/school account (Microsoft Entra ID / Azure AD)

- **Default:** use an approved App Registration owned by the target organization with `--tenant-id organizations` (or tenant GUID).
- **Optional:** if your organization already has an approved App Registration, use `--client-id <your-app-id>` and `--tenant-id <tenant-id>`. See [Create Your Own App Registration](../docs/app-registration.md) for portal steps.
- **Suggested scopes** (for your own app):
  - `Mail.ReadWrite`
  - `Mail.Send`
  - `Calendars.ReadWrite`
  - `Files.ReadWrite.All`
  - `Contacts.ReadWrite` *(remove if contacts are not needed)*
  - `offline_access` (required for refresh token)

## Assisted device-code flow

1. Run (personal-account profile): `python3 scripts/graph_auth.py device-login --tenant-id consumers`  
   Or work/school: `python3 scripts/graph_auth.py device-login --client-id <approved-app-id> --tenant-id organizations`
2. The script prints **URL** and **code**.
3. Open `https://microsoft.com/devicelogin`, paste the code, and authorize.
4. On success, the script saves `~/.openclaw/graph/personal-token.json` with `access_token`, `refresh_token`, expiration, and scopes.
5. Tokens auto-refresh before requests. To force refresh: `python3 scripts/graph_auth.py refresh`.
6. Scopes default to the personal OneDrive read-only baseline. Add scopes explicitly only when enabling modules:
   ```bash
   python3 scripts/graph_auth.py device-login \
     --scope User.Read \
     --scope Files.ReadWrite \
     --scope offline_access
   ```

## `~/.openclaw/graph/personal-token.json` structure

```json
{
  "client_id": "e8ee2c58-635e-491f-99f7-c60b63b70f64",
  "tenant_id": "consumers",
  "scopes": ["User.Read", "Files.Read", "offline_access"],
  "token": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": 1234567890
  }
}
```

Never commit this file. It lives outside the repo by default and is written with `0600` permissions.

## Common errors

| Symptom | Fix |
| --- | --- |
| `authorization_pending` | Wait, user has not completed authorization yet. |
| `interaction_required` | Re-run device login (token invalid/consent removed). |
| `AADSTS50059` on `/devicecode` | Tenant is incompatible with account type. For personal accounts use `--tenant-id consumers`. |
| `AADSTS700016` on `consumers` | `client_id` is not valid for Microsoft personal accounts. Use an MSA-compatible app registration. |
| `AADSTS70011 invalid_scope` with `OnlineMeetings.*` on `consumers` | `OnlineMeetings.*` scopes are not supported in this workflow for personal accounts. Remove these scopes and keep default scopes. |
| Repeated 401 errors | Run `graph_auth.py refresh`; if still failing, run `clear` and re-authenticate. |
| 403 (Access Denied) | Add the required scope and grant consent again. |
