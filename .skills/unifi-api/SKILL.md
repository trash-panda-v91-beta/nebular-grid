---
name: unifi-api
description: Use when interacting with the UniFi Network API v10.1.84 — automating network tasks, querying devices/clients/stats, managing firewall rules, networks, WiFi, vouchers, ACLs, or DNS policies via the REST API.
---

# UniFi Network API v10.1.84

## Overview

REST API for UniFi Network Application (self-hosted). Auth via API key header. All site-scoped resources require a `siteId` UUID.

- **Base URL:** `https://<host>/integration/v1`
- **Docs:** https://developer.ui.com/network/v10.1.84
- **Full reference:** See `reference.md` in this skill directory

---

## Authentication

```http
X-API-KEY: <your-api-key>
```

Generate keys under **Settings → Integrations** in the UniFi application. Keys are scoped per organization.

---

## Critical First Step: Get Your Site ID

**All resources are site-scoped.** Always fetch the site ID first:

```bash
GET /v1/sites
# Response: { data: [{ id: "uuid", name: "Default" }] }
```

---

## Pagination

All list responses use this envelope:
```json
{ "offset": 0, "limit": 25, "count": 10, "totalCount": 100, "data": [...] }
```
Query params: `offset`, `limit`, `filter`

---

## Filter Syntax

```
eq(name,"value")          # exact match
ne(id,"uuid")             # not equal
in(state,["ON","OFF"])    # one of list
contains(name,"partial")  # substring
and(expr1,expr2)          # compound
or(expr1,expr2)
not(expr)
```

---

## Quick Reference

| Resource | Base Path |
|----------|-----------|
| Sites | `/v1/sites` |
| Devices | `/v1/sites/{siteId}/devices` |
| Clients | `/v1/sites/{siteId}/clients` |
| Networks | `/v1/sites/{siteId}/networks` |
| WiFi SSIDs | `/v1/sites/{siteId}/wifi/broadcasts` |
| Firewall Zones | `/v1/sites/{siteId}/firewall/zones` |
| Firewall Policies | `/v1/sites/{siteId}/firewall/policies` |
| ACL Rules | `/v1/sites/{siteId}/acl-rules` |
| DNS Policies | `/v1/sites/{siteId}/dns/policies` |
| Hotspot Vouchers | `/v1/sites/{siteId}/hotspot/vouchers` |
| Traffic Lists | `/v1/sites/{siteId}/traffic-matching-lists` |
| VPN Tunnels | `/v1/sites/{siteId}/vpn/site-to-site-tunnels` |
| VPN Servers | `/v1/sites/{siteId}/vpn/servers` |
| WANs | `/v1/sites/{siteId}/wans` |
| DPI Categories | `/v1/dpi/categories` |
| DPI Applications | `/v1/dpi/applications` |

---

## Common Patterns

### List connected clients (wireless only)
```http
GET /v1/sites/{siteId}/clients?filter=eq(type,"WIRELESS")
```

### Get device stats
```http
GET /v1/sites/{siteId}/devices/{deviceId}/statistics/latest
```
Returns: `uptimeSec`, `cpuUtilizationPct`, `memoryUtilizationPct`, `uplink.txRateBps/rxRateBps`

### Restart a device
```http
POST /v1/sites/{siteId}/devices/{deviceId}/actions
{ "action": "RESTART" }
```

### Power-cycle a PoE port
```http
POST /v1/sites/{siteId}/devices/{deviceId}/interfaces/ports/{portIdx}/actions
{ "action": "POWER_CYCLE" }
```

### Create a guest voucher
```http
POST /v1/sites/{siteId}/hotspot/vouchers
{ "count": 1, "name": "Guest", "timeLimitMinutes": 480, "dataUsageLimitMBytes": 1000 }
```

### Authorize a guest client
```http
POST /v1/sites/{siteId}/clients/{clientId}/actions
{ "action": "AUTHORIZE_GUEST_ACCESS" }
```

### Create a firewall zone
```http
POST /v1/sites/{siteId}/firewall/zones
{ "name": "IoT", "networkIds": ["uuid"] }
```

---

## Error Response Shape

```json
{
  "statusCode": 404,
  "statusName": "NOT_FOUND",
  "code": "RESOURCE_NOT_FOUND",
  "message": "Human-readable explanation",
  "timestamp": "...",
  "requestPath": "...",
  "requestId": "uuid"
}
```

---

## Key Notes

- **Metadata origins:** `USER_DEFINED` (editable/deletable), `SYSTEM_DEFINED` (built-in, no delete), `DERIVED` (auto-generated, read-only), `ORCHESTRATED` (external system managed)
- **Firewall zones:** Only `USER_DEFINED` zones can be deleted
- **Networks:** `vlanId` 1 = default network; valid custom range is 2–4009
- **Policy ordering:** Firewall policies and ACL rules have separate ordering endpoints — use `GET .../ordering` + `PUT .../ordering` to reorder
- **PATCH support:** Only `patchFirewallPolicy` supports partial update (only `loggingEnabled` field)
- **DNS TXT records:** Values containing commas must be wrapped in double quotes

---

## Full Reference

See `reference.md` for complete endpoint index, all request/response schemas, WiFi broadcast config, firewall policy traffic filter types, and ACL rule shapes.
