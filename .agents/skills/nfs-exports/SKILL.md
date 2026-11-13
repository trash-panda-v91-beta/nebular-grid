---
name: nfs-exports
description: Use when an app mounts the NAS over NFS, a new export is needed on the TrueNAS box, or an existing export is being changed - `/mnt/tank` paths, `type: nfs` in an app-template persistence block, "give it storage on the NAS". Auto-fires before creating or editing an export.
---

# NFS exports on the NAS

The NAS (`asc`) serves `/mnt/tank/*` over **NFSv4 only**. Every consumer is a pod, and cilium masquerades pod traffic to the node IP, so the NAS sees `10.1.10.21-23` and never a pod address. That is why exports are scoped by node network, not by client application.

## Creating an export

1. **Dataset first.** App data goes in `/mnt/tank/apps/<app>`, backup repositories in `/mnt/tank/backup/<name>`. Put a quota on the dataset, not on the pool.
2. **Export it** with:
   - `networks: ["10.1.10.0/25"]` - the static half of the Servers VLAN. Empty `hosts` **and** empty `networks` means the export is open to anything that can reach 2049. Never list node IPs individually: the next node swap breaks the mount silently.
   - `comment: "k8s: <app>"` so the export list stays readable.
   - `mapall_user: psb` when the image writes as an arbitrary uid and the files should end up owned by one user. Leave the mapping empty when the app runs as root in the container and expects root-owned files.
   - `ro: false` in practice - no consumer today is genuinely read-only.
3. **Reload:** `POST /service/reload` with `{"service": "nfs"}`. Skipping it leaves clients on "No such file or directory" until something else restarts NFS.
4. **Reference it** in the app as `type: nfs`, `server: asc.sto.bar.internal`, `path: /mnt/tank/...`. Use the `.internal` name, not the UI name.

## Verify

- Inside the app pod: `df -h | grep :/mnt/tank` shows the mount and `ls` on the mountpoint works.
- `GET /nfs/get_nfs4_clients` lists client addresses. Anything other than the three node IPs means something outside the cluster is mounting.
- A fresh `Snapshot` reaching `Ready` proves writes still work.

## API access

`https://asc.nebular-grid.space/api/v2.0` with `Authorization: Bearer $TRUENAS_API_KEY` (in `fnox`).

| call | what |
|---|---|
| `GET /sharing/nfs` | every export with its ACL |
| `PUT /sharing/nfs/id/<id>` | update one (send only the fields from the update schema) |
| `GET /nfs/get_nfs4_clients` | who is mounted right now |
| `POST /service/reload` | apply an export change |

## Traps

- `showmount -e` does not work against this NAS: NFSv3 is off and it fails with "program/version mismatch". Use the API.
- `sec=sys` everywhere. NFS trusts whatever uid the client claims, so the network ACL is the only control. Do not widen it for convenience.
- An export cannot be read-only for one consumer only. `/mnt/tank/media` is shared by the whole *arr stack plus jellyfin and youtarr.
- A new dataset gets no backup by itself. kopiur and volsync need their own export and their own policy.
