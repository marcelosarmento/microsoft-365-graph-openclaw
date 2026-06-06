# Mail Reference

## Profile selection

Choose the mailbox context before reading, moving, or sending mail. Recommended for agents/OpenClaw: use `GRAPH_PROFILE=personal` or `GRAPH_PROFILE=work` for a per-command choice, or pass `--profile <name>` to `mail_fetch.py` / `mail_send.py`. If omitted, the backward-compatible `default` profile is used. See [`auth.md`](auth.md).

## Listing

```
python scripts/mail_fetch.py --folder Inbox --top 10 --unread
```

- `--filter` accepts OData expressions (`contains(subject,'Status')`).
- `--id <messageId>` fetches a specific message.
- `--include-body` returns full body content (HTML + text).
- `--mark-read` and `--move-to <folderId>` act on the message loaded with `--id`.

## Sending

```
python scripts/mail_send.py \
  --to user@example.com \
  --subject "Follow-up" \
  --body-file drafts/reply.html --html \
  --cc teammate@example.com \
  --attachment docs/proposal.pdf
```

- `saveToSentItems` is `True` by default. Use `--no-save-copy` to disable.
- Attachments are sent as `fileAttachment` and are limited on this endpoint; for large files, implement upload session flow.

## Useful folder IDs

List folders with:
```
curl -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://graph.microsoft.com/v1.0/me/mailFolders
```
Or query a known folder with `mail_fetch.py --folder SentItems`.

## Push-mode boundary

Daily mail work should use the list/fetch/send commands above. Do **not** start webhook servers, create subscriptions, or run privileged setup scripts unless the user explicitly asks for push-mode setup or webhook operations.

For already-configured push-mode status and subscription commands, see [`references/mail_webhook_adapter.md`](mail_webhook_adapter.md). For setup, EC2/Caddy/systemd, smoke tests, and privileged runbooks, see [`../ops/mail-webhook.md`](../ops/mail-webhook.md).
