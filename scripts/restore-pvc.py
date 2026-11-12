#!/usr/bin/env python3
"""Restore PVCs from kopiur snapshots using the volume-populator flow.

Per PVC: scale the workloads that mount it to zero, delete the PVC, create a
Restore (target.populator) plus a PVC claiming it via dataSourceRef, wait for
the claim to bind, then scale the workloads back.

Restores fail loudly (onMissingSnapshot: Fail) so a missing snapshot never
produces a silently empty volume.
"""
import argparse
import json
import subprocess
import sys
import time

KUBECTL = ["kubectl", "--request-timeout=30s"]


def run(*args, check=True):
    r = subprocess.run(KUBECTL + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("kubectl %s: %s" % (" ".join(args), r.stderr.strip()))
    return r


def kjson(*args):
    out = run(*args).stdout
    return json.loads(out) if out.strip() else None


def policy_map(namespace):
    d = kjson("get", "snapshotpolicies.kopiur.home-operations.com", "-n", namespace, "-o", "json")
    mapping = {}
    for item in d.get("items", []):
        for src in item["spec"].get("sources", []):
            pvc = (src.get("pvc") or {}).get("name")
            if pvc:
                mapping[pvc] = item["metadata"]["name"]
    return mapping


def succeeded_snapshot(namespace, policy):
    d = kjson("get", "snapshots.kopiur.home-operations.com", "-n", namespace, "-o", "json")
    names = [s["metadata"]["name"] for s in d.get("items", [])
             if s.get("status", {}).get("phase") == "Succeeded"
             and (s["metadata"]["name"].startswith(policy + "-")
                  or (s.get("spec") or {}).get("policy") == policy)]
    return sorted(names)[-1] if names else None


def owners(namespace, pvc):
    found = []
    for kind in ("deploy", "sts"):
        d = kjson("get", kind, "-n", namespace, "-o", "json")
        for item in d.get("items", []):
            vols = item["spec"]["template"]["spec"].get("volumes") or []
            if any((v.get("persistentVolumeClaim") or {}).get("claimName") == pvc for v in vols):
                found.append((kind, item["metadata"]["name"],
                              item.get("spec", {}).get("replicas", 1)))
    return found


def wait_gone(namespace, pvc, limit=120):
    end = time.time() + limit
    while time.time() < end:
        r = run("get", "pvc", pvc, "-n", namespace, check=False)
        if r.returncode != 0:
            return True
        time.sleep(5)
    return False


def wait_bound(namespace, pvc, limit=1200):
    end = time.time() + limit
    while time.time() < end:
        r = run("get", "pvc", pvc, "-n", namespace, "-o", "jsonpath={.status.phase}", check=False)
        if r.returncode == 0 and r.stdout.strip() == "Bound":
            return True
        time.sleep(10)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--namespace", action="append", default=[])
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    namespaces = args.namespace or [
        "ai", "database", "downloads", "home-automation", "media", "selfhosted",
        "observability", "security",
    ]
    failed = []
    for ns in namespaces:
        pmap = policy_map(ns)
        pvcs = kjson("get", "pvc", "-n", ns, "-o", "json").get("items", [])
        if not pvcs:
            continue
        print("== %s (%d pvc)" % (ns, len(pvcs)), flush=True)
        for p in pvcs:
            name = p["metadata"]["name"]
            size = p["spec"]["resources"]["requests"]["storage"]
            sc = p["spec"].get("storageClassName")
            pol = pmap.get(name)
            if not pol:
                print("  skip (no policy): %s/%s" % (ns, name), flush=True)
                continue
            snap = succeeded_snapshot(ns, pol)
            if not snap:
                print("  skip (no succeeded snapshot): %s/%s policy=%s" % (ns, name, pol), flush=True)
                continue
            r0 = run("get", "restore.kopiur.home-operations.com", "%s-restore" % name,
                     "-n", ns, "-o", "jsonpath={.status.phase}", check=False)
            if r0.returncode == 0 and r0.stdout.strip() in ("Restoring", "Ready", "Completed"):
                print("  skip (restore already %s): %s/%s" % (r0.stdout.strip(), ns, name), flush=True)
                continue
            work = owners(ns, name)
            print("  plan %s/%s %s %s policy=%s snap=%s" % (ns, name, size, sc, pol, snap), flush=True)
            if not args.execute:
                continue

            for kind, wname, _ in work:
                run("scale", "%s/%s" % (kind, wname), "-n", ns, "--replicas=0")
            time.sleep(20)

            r = run("delete", "pvc", name, "-n", ns, "--ignore-not-found", "--wait=false", check=False)
            if not wait_gone(ns, name):
                print("  FAILED (pvc will not go away): %s/%s" % (ns, name), flush=True)
                for kind, wname, reps in work:
                    run("scale", "%s/%s" % (kind, wname), "-n", ns, "--replicas=%d" % (reps or 1))
                failed.append("%s/%s" % (ns, name))
                continue

            restore = {
                "apiVersion": "kopiur.home-operations.com/v1alpha1",
                "kind": "Restore",
                "metadata": {"name": "%s-restore" % name, "namespace": ns},
                "spec": {
                    "credentialProjection": {"enabled": True},
                    "mover": {"securityContext": {"runAsUser": 2000, "runAsGroup": 2000}},
                    "policy": {"onMissingSnapshot": "Fail"},
                    "source": {"fromPolicy": {"name": pol, "offset": 0}},
                    "target": {"populator": {}},
                },
            }
            claim = {
                "apiVersion": "v1",
                "kind": "PersistentVolumeClaim",
                "metadata": {"name": name, "namespace": ns},
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": size}},
                    **({"storageClassName": sc} if sc else {}),
                    "dataSourceRef": {
                        "apiGroup": "kopiur.home-operations.com",
                        "kind": "Restore",
                        "name": "%s-restore" % name,
                    },
                },
            }
            subprocess.run(KUBECTL + ["apply", "-f", "-"],
                           input=json.dumps({"apiVersion": "v1", "kind": "List",
                                             "items": [restore, claim]}),
                           text=True, capture_output=True, check=True)

            if wait_bound(ns, name):
                print("  DONE %s/%s" % (ns, name), flush=True)
            else:
                print("  TIMEOUT %s/%s" % (ns, name), flush=True)
                failed.append("%s/%s" % (ns, name))

            for kind, wname, reps in work:
                run("scale", "%s/%s" % (kind, wname), "-n", ns, "--replicas=%d" % (reps or 1))

    if failed:
        print("failed: %s" % ", ".join(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
