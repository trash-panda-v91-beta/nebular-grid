---
name: add-docker-app
description: Use when deploying or changing an application on the TrueNAS docker host - docker-compose stacks under docker/truenas/, doco-cd deployments, "deploy X to the NAS"
---

# Add an App to the TrueNAS Docker Host

Apps live in `docker/truenas/<app>/docker-compose.yaml`, deployed GitOps-style by [doco-cd](https://github.com/kimdre/doco-cd) (config: `docker/truenas/.doco-cd/docker-compose.yaml`): it polls this repo's `main` branch and auto-discovers stacks one directory deep. **Removing (or renaming) a directory deletes the running stack**.

Current apps are minimal - mirror an existing one rather than inventing structure:

| Reference app | Shows |
|---|---|
| `node-exporter` | Host network, bind mounts |
| `smartctl-exporter` | Privileged, published ports |

## Steps

1. **Directory**: create `docker/truenas/<app>/docker-compose.yaml`.

2. **Compose file** - conventions from existing apps:
   - `restart: always` or `restart: unless-stopped`.
   - Registry-qualified image with a pinned version tag. **Never write a tag from memory** - look up the upstream project's current release first.
   - Config files and persistent data via bind mounts to host paths.
   - `network_mode: host` for exporters; publish `ports:` for apps that need external access.

3. **Secrets**: the current doco-cd config does not use `external_secrets`. If secrets are needed, hardcode them in the compose file (this repo's docker side is minimal) or extend the doco-cd compose with 1Password integration.

4. **Verify**: `docker compose -f docker/truenas/<app>/docker-compose.yaml config --quiet`. Show the user the files before committing. Commit style: `feat(<app>): Deploy to NAS`.

## Common mistakes

- **Inventing an image tag** - check the upstream release; a hallucinated tag deploys nothing or the wrong thing.
- **Renaming an existing app directory casually** - doco-cd tears the old stack down on removal.
- **Forgetting `restart: always`** - containers won't survive host reboots.