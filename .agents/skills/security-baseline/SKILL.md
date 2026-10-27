---
name: security-baseline
description: >
  Use when adding an app, namespace, HTTPRoute, ExternalSecret or HelmRelease to
  nebular-grid, when reviewing a change to one, or when asked "is this secure".
  The cluster security standard as a checklist plus the commands that verify it.
  Auto-fires before writing a HelmRelease securityContext block, a namespace, a
  route, or a secret reference.
---

# Security baseline

Rules this cluster is held to. Checkable in a minute. Single admin, single tenant, one 1Password vault - the standard is sized for that, not for a multi-tenant cluster.

## Threat model

Defend against: accidental public exposure, one compromised workload reaching the vault or the database, credential sprawl.

Not defended: someone with cluster-admin already, an attacker with a node foothold. Do not build for those. Pretending otherwise is how a home lab becomes an unpaid job.

## New app checklist

Copy-paste shapes, all of them required unless the line says otherwise.

### 1. Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: _
  annotations:
    kustomize.toolkit.fluxcd.io/prune: disabled
  labels:
    pod-security.kubernetes.io/enforce: restricted   # baseline | privileged, see below
```

Levels: `restricted` for app namespaces. `baseline` for infra needing one specific capability. `privileged` for the hardware namespaces only - `kube-system`, `rook-ceph`, `observability`, `network`, `home-automation`. A new namespace asking for `privileged` is a bug, not a config.

### 2. Pod securityContext

Every container, no exceptions, because the cluster has no default:

```yaml
defaultPodOptions:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
    seccompProfile:
      type: RuntimeDefault
containers:
  app:
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop: ["ALL"]
```

If the app writes to its own directory, mount an `emptyDir` and keep `readOnlyRootFilesystem: true`. Dropping the rule is the last resort, not the first.

### 3. Secrets

Never a value in git. Always an `ExternalSecret` -> `ClusterSecretStore onepassword`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: myapp
spec:
  refreshInterval: 12h
  secretStoreRef:
    kind: ClusterSecretStore
    name: onepassword
  target:
    name: myapp-secret
  data:
    - secretKey: password
      remoteRef:
        key: myapp
        property: password
```

Prefer `data` with named properties over `dataFrom.extract` - extract pulls every field of the item.

### 4. Route

Internal by default:

```yaml
route:
  app:
    hostnames: ["myapp.${SECRET_DOMAIN}"]
    parentRefs:
      - name: envoy-internal
        namespace: network
```

Never `envoy-external` unless the user explicitly asked for public access. Public requires both: the `expose: public` label on the namespace, and auth in front of the route (OIDC via kanidm, or a `SecurityPolicy` basic auth).

Public route for a workload running in `flux-system` or `cilium-secrets`: put the `HTTPRoute` in `network` and add a `ReferenceGrant` in the backend namespace. Those namespaces cannot carry the label - flux-operator marks them `ssa: Ignore` and strips hand-applied labels.

### 5. Network policy

Default-deny ingress in the app namespace, plus an explicit allow for the gateway and for Prometheus in `observability`. A namespace without a policy is reachable from every pod in the cluster.

## Verify before merging

```bash
kubectl kustomize clusters/psb/apps/<ns>/<app>/app    # renders?
```

After merging:

```bash
flux get ks -A | grep -v True                          # nothing stuck
kubectl -n <ns> get pods                               # running, not CrashLoop
kubectl -n <ns> get hr <app> -o yaml | grep -E 'Ready|message'
kubectl get externalsecret -A | grep -v SecretSynced   # secrets still syncing
kubectl get httproute -A -o wide                       # route attached
```

Route attachment check, whole cluster (expect 0 bad):

```bash
kubectl get httproute -A -o json | jq -r '
  .items[] as $r | ($r.status.parents // [])[] |
  {ns: $r.metadata.namespace, name: $r.metadata.name, gw: .parentRef.name,
   ok: ([.conditions[] | select(.type=="Accepted" or .type=="ResolvedRefs") | (.status=="True")] | all)}
  | select(.ok|not) | "\(.ns)/\(.name) on \(.gw)"'
```

## Rules that are not per-app

- Only the Flux controllers and flux-operator hold `cluster-admin`. Nothing else.
- App service accounts get no RBAC. A pod must not be able to create Secrets, ExternalSecrets, HTTPRoutes or Gateways - that is what makes the single-vault limitation survivable. Re-check with `kubectl auth can-i create secrets -n <ns> --as=system:serviceaccount:<ns>:default` whenever RBAC changes.
- Images pinned by digest, renovate proposes, CI checks, human merges.
- Nothing lands except through a PR. No out-of-band `kubectl apply/edit/label`. The one exception: deleting an object git cannot prune (a Kustomization with `prune: false` left an orphan) - record it.
- One change per PR, verify after each. A security change that breaks a service teaches everyone to ignore security changes.
- Never print a secret. Verify with a status code or a length, not `cat`.

## Known limits, accepted on purpose

- ESO's 1Password provider cannot scope below vault level. One vault means any namespace allowed to use the store can read any item in it. Rely on the RBAC rule above rather than inventing per-namespace stores that isolate nothing.
- The cluster-wide `allow-cluster-egress` policy allows `toEntities: world` for every endpoint, so egress is effectively open. Fixing it means designing per-app egress; until then do not pretend it controls anything.
- No policy engine. Admission policy is the right answer once the same rule gets broken twice by hand. Then: a few `ValidatingAdmissionPolicy` objects, not Kyverno.
