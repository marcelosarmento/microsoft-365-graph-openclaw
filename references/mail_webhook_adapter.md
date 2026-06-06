# Mail Push Operations Reference

Use this file only when the user asks about an already-configured mail push/webhook workflow, subscription status, renewal, queue inspection, or webhook health.

For first-time setup, EC2/Caddy/systemd installation, OpenClaw hook configuration, smoke tests, privileged scripts, and end-to-end bootstrap, use [`../ops/mail-webhook.md`](../ops/mail-webhook.md) instead.

## Agent decision boundary

- Prefer ordinary mail commands in [`mail.md`](mail.md) for daily inbox work.
- Use push-mode commands here only for operational checks or subscription maintenance.
- Do not run `sudo`, write `/etc`, edit Caddy/systemd, or patch OpenClaw config from this reference.
- Use `--hook-action agent` only when explicitly requested; default push behavior is `wake` to `/hooks/wake`.

## Components

- `scripts/mail_webhook_adapter.py`: HTTP endpoint for Graph validation and notification enqueue.
- `scripts/mail_subscriptions.py`: subscription lifecycle (`create`, `status`, `renew`, `delete`, `list`).
- `scripts/mail_webhook_worker.py`: async queue processing, dedupe, and OpenClaw wake/hook delivery.

Defaults:
- Subscription resource: `me/messages`.
- Worker action: `wake` (`/hooks/wake`, `mode=now`).
- Queue files:
  - `state/mail_webhook_queue.jsonl`
  - `state/mail_webhook_dedupe.json`

## Runtime values

These are typically loaded by services from `/etc/default/graph-mail-webhook` after setup:

- `GRAPH_WEBHOOK_CLIENT_STATE`: secret used by Graph subscription and adapter validation.
- `OPENCLAW_HOOK_URL`: OpenClaw hook endpoint, usually `/hooks/wake`.
- `OPENCLAW_HOOK_TOKEN`: OpenClaw hook token.
- `OPENCLAW_SESSION_KEY`: optional routing key; default `hook:graph-mail`.

Do not print token values in user-visible logs.

## Safe subscription commands

List subscriptions:

```bash
python3 scripts/mail_subscriptions.py list
```

Check one subscription:

```bash
python3 scripts/mail_subscriptions.py status --id "<subscription-id>"
```

Renew one subscription:

```bash
python3 scripts/mail_subscriptions.py renew \
  --id "<subscription-id>" \
  --minutes 4200
```

Create a subscription only when the public HTTPS endpoint and `GRAPH_WEBHOOK_CLIENT_STATE` are already configured:

```bash
python3 scripts/mail_subscriptions.py create \
  --notification-url "https://graph-hook.example.com/graph/mail" \
  --client-state "$GRAPH_WEBHOOK_CLIENT_STATE" \
  --minutes 4200
```

## Local/manual runtime commands

Start adapter in the foreground:

```bash
python3 scripts/mail_webhook_adapter.py serve \
  --host 0.0.0.0 \
  --port 8789 \
  --path /graph/mail \
  --client-state "$GRAPH_WEBHOOK_CLIENT_STATE"
```

Run worker in the foreground:

```bash
python3 scripts/mail_webhook_worker.py loop \
  --session-key "$OPENCLAW_SESSION_KEY" \
  --hook-url "$OPENCLAW_HOOK_URL" \
  --hook-token "$OPENCLAW_HOOK_TOKEN"
```

## Health checks

Confirm service evidence if systemd setup already exists:

```bash
journalctl -u graph-mail-webhook-adapter --since "15 minutes ago" | rg 'POST /graph/mail HTTP/1.1" 202'
```

Check queued notifications:

```bash
wc -l state/mail_webhook_queue.jsonl
```

Check worker processing outcomes:

```bash
tail -n 80 state/graph_ops.log | rg 'mail_webhook_processed|mail_webhook_drop_max_retries'
```

For full pipeline diagnostics that may need `sudo`, see [`../ops/mail-webhook.md`](../ops/mail-webhook.md).

## Troubleshooting signals

| Symptom | Action |
| --- | --- |
| Subscription create returns `400 ValidationError` | Confirm public HTTPS endpoint echoes Graph validation token. |
| Notifications rejected | Confirm `clientState` in subscription matches adapter env. |
| Queue grows | Worker or OpenClaw hook may be unavailable; inspect worker logs. |
| Repeated duplicates | Check Graph retry behavior and dedupe state. |
| 401/403 fetching messages | Refresh auth and confirm `Mail.ReadWrite` consent. |
