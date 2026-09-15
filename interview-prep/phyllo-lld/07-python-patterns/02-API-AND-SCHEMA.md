# APIs + Schema Cheat Reference

---

## Core REST surface (Phyllo-like)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/users` | Create end user |
| POST | `/v1/sdk-tokens` | Short-lived Connect token |
| GET | `/v1/accounts` | List connected accounts |
| GET | `/v1/accounts/{id}` | Account + sync statuses |
| GET | `/v1/profiles/{account_id}` | Identity profile |
| GET | `/v1/accounts/{id}/contents` | Paginated content |
| POST | `/v1/contents/bulk` | Hydrate up to 100 IDs |
| GET | `/v1/users/{id}/income/summary` | Income aggregate |
| POST | `/v1/webhooks` | Register webhook |
| POST | `/v1/creator-search` | Public discovery |

Errors to mention: `401`, `403`, `404`, `409`, `422`, `429`, `500`.

---

## Minimal schema (draw fast)

```
developers
users(developer_id, external_user_id UNIQUE pair)
accounts(user_id, work_platform_id, status, external_account_id UNIQUE per platform)
consents(account_id, product, status)
oauth_credentials(account_id PK, tokens encrypted)
sync_jobs(account_id, product, status, cursor, locked_until)
profiles(account_id PK, handle, followers, payload_json, updated_at)
content_items(account_id, platform_content_id UNIQUE pair, published_at, metrics_json)
income_transactions(account_id, platform_txn_id UNIQUE pair, amount, currency, occurred_at)
webhook_subscriptions(developer_id, url, secret, events[])
webhook_deliveries(subscription_id, event_id UNIQUE pair, status, retry_count)
outbox(id, event_type, payload, published_at)
```

---

## Indexes worth saying

- `content_items(account_id, published_at DESC)`  
- `sync_jobs(status, locked_until)`  
- `webhook_deliveries(status, next_attempt_at)`  
- `income_transactions(account_id, occurred_at)`  

---

## Example request/response (Connect token)

```json
POST /v1/sdk-tokens
{
  "user_id": "usr_123",
  "products": ["IDENTITY", "ENGAGEMENT"],
  "client_display_name": "BrandApp"
}

→ { "sdk_token": "tok_...", "expires_at": "..." }
```
