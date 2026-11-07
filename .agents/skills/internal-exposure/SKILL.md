---
name: internal-exposure
description: >
  Use when deploying services, creating HTTPRoutes, configuring DNS records,
  or exposing anything to the network in nebular-grid - never expose a service
  to the public internet unless the user explicitly asks. Internal services use
  the envoy-internal gateway, which gets its DNS from external-dns
  automatically. Auto-fires before writing any HelmRelease route block, DNS
  record, or gateway reference.
---

# Internal Exposure Rule

**Never expose anything externally unless the user explicitly asks.** This
includes public DNS records, Cloudflare-proxied routes, public gateways, and
`external-dns` managed hostnames. When in doubt, ask.

## Gateways in nebular-grid

| Gateway | DNS | Reachable from |
|---------|-----|----------------|
| `envoy-internal` | external-dns writes a CNAME to `ingress-int-psb.nebular-grid.space` | LAN and VPN |
| `envoy-external` | external-dns writes a **public** record | The internet - **only on explicit request** |

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

1. Route `parentRefs` -> `envoy-internal`
2. Do **not** add the `external-dns.kubernetes.io/cloudflare-proxied`
   annotation and do **not** point the route at `envoy-external` - those publish
   the name to the public zone on Cloudflare. Internal names resolve from the
   gateway for LAN and VPN clients and must not be enumerable from the internet.
3. DNS is **automatic**. `envoy-internal` carries
   `external-dns.kubernetes.io/target: ingress-int-psb.nebular-grid.space`, so
   external-dns-unifi writes a CNAME to it and the gateway answers. No manual
   UniFi record is needed for a route hostname.
   - A record in UniFi is only for something that is **not** an HTTPRoute - a
     device, a NAS share, a load balancer IP. Point those at the address directly
     (unifi MCP: `unifi_create_dns_record`, then enable it - records are created
     `enabled: false`).
   - Never set `local_dns_record` on a DHCP reservation: it shadows the
     automatic `<device>.<room>.<site>.internal` name with a competing one.
4. Verify with `dig <host> @10.1.0.1` - DNS propagation can take a moment and
   negative lookups get cached.

## Gotchas

- **Do not test public DNS with `dig @8.8.8.8` from inside the house.** The
  gateway intercepts LAN DNS and answers it, so you are querying UniFi and
  calling it the internet. This has produced wrong conclusions more than once.
  Use DNS-over-HTTPS, which cannot be intercepted:

  ```
  curl -s -H 'accept: application/dns-json' \
    'https://dns.google/resolve?name=NAME&type=A'
  ```

- **To prove which resolver a client actually uses,** create a name that exists
  in only one place (a UniFi record and nowhere else) and ask the client for it.
  If it answers, the client is using the gateway. Delete the probe afterwards.
- The VPN must **push DNS** for any of this to work off-LAN. `dhcpd_dns_enabled`
  has to be true on the VPN network, not just `dhcpd_dns_1` set - the flag is off
  by default and iOS silently keeps its own resolver.
- `envoy-external` is the only gateway whose names go to Cloudflare. It carries
  the `external-dns/controller: externaldns-cloudflare` label; `envoy-internal`
  deliberately does not.
- The 1Password **service account** (`OP_SERVICE_ACCOUNT_TOKEN`) sees only the
  `NebularGrid` vault - `Private` vault references do not resolve in fnox or
  `op`
- Secret values must never be printed: pipe them (`curl ... | fnox set`,
  `pbcopy`) and verify with status codes or length checks
