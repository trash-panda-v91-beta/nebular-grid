---
name: internal-exposure
description: >
  Use when deploying services, creating HTTPRoutes, configuring DNS records,
  or exposing anything to the network in nebular-grid - never expose a service
  to the public internet unless the user explicitly asks. Internal services use
  the envoy-internal or envoy-internal-vpn gateway plus a UniFi DNS record.
  Auto-fires before writing any HelmRelease route block, DNS record, or
  gateway reference.
---

# Internal Exposure Rule

**Never expose anything externally unless the user explicitly asks.** This
includes public DNS records, Cloudflare-proxied routes, public gateways, and
`external-dns` managed hostnames. When in doubt, ask.

## Gateways in nebular-grid

| Gateway | DNS | Reachable from |
|---------|-----|----------------|
| `envoy-internal` | UniFi DNS record (manual) | LAN only |
| `envoy-internal-vpn` | UniFi DNS record (manual) | VPN only |
| `envoy-internal-public-dns` | external-dns creates a **public** record | Externally - **only on explicit request** |

## Public gateway needs a namespace label

`envoy-external` only accepts HTTPRoutes from namespaces labelled
`expose: public`. Adding that label is the decision to let a namespace publish,
so ask first.

`flux-system` cannot carry the label: flux-operator owns that namespace and
marks it `kustomize.toolkit.fluxcd.io/ssa: Ignore`, so kustomize-controller skips
it and any label added from git is ignored. A hand-applied label is stripped by
the operator too. Public routes for services that run in `flux-system` therefore
live in `network` (`envoy-gateway/config/public-routes.yaml`) and reach the
backend through a `ReferenceGrant` in `flux-system`. Do the same for anything
else that has to publish from an operator-owned namespace.

## Internal service checklist

1. Route `parentRefs` -> `envoy-internal` (or `envoy-internal-vpn`)
2. Do **not** add the `external-dns.kubernetes.io/cloudflare-proxied`
   annotation and do **not** use `envoy-internal-public-dns` - those create
   public DNS records
3. Create a **UniFi DNS record** pointing the hostname at the internal
   ingress IP `10.1.6.43` (unifi MCP: `unifi_create_dns_record`, then enable
   it - records are created `enabled: false`)
4. Verify with `nslookup <host>` against the UniFi resolver (`10.1.0.1`) -
   DNS propagation can take a moment and negative lookups get cached

## Gotchas

- `envoy-internal` routes get **no DNS record automatically** - "Server Not
  Found" in a browser means the UniFi record is missing, not that the gateway
  is wrong
- The 1Password **service account** (`OP_SERVICE_ACCOUNT_TOKEN`) sees only the
  `NebularGrid` vault - `Private` vault references do not resolve in fnox or
  `op`
- Secret values must never be printed: pipe them (`curl ... | fnox set`,
  `pbcopy`) and verify with status codes or length checks
