set quiet := true
set shell := ['bash', '-euo', 'pipefail', '-c']

root := justfile_dir()
psb_dir := root + '/clusters/psb'
talos_dir := psb_dir + '/talos'

[private]
default:
  just -l psb talos

[private]
controller:
  @talosctl config info --output json | jq --raw-output '.endpoints[]' | shuf -n 1

[private]
nodes:
  @talosctl config info -o yaml | yq -e '.nodes | join (",")'

[doc('Apply Talos config to a node')]
apply-node node *args:
  just log info "Applying Talos machineconfig" "node" "{{ node }}";
  just psb talos render-config "{{ node }}" | talosctl -n "{{ node }}" apply-config -f /dev/stdin {{ args }}

[doc('Apply Talos config to all nodes in the cluster')]
apply-cluster *args:
  kubectl get nodes --no-headers | while read -r node _; do \
    just psb talos apply-node ${node} {{ args }}; \
  done

[doc('Generate schematic ID from Talos schematic')]
gen-schematic-id:
  curl -sX POST --data-binary "@{{ talos_dir }}/schematic.yaml" "https://factory.talos.dev/schematics" | jq -r '.id'

[doc('Render Talos config for a node')]
render-config node:
  export IS_CONTROLPLANE="$(just psb talos machine-controller {{ node }})"; \
  talosctl machineconfig patch <(just template "{{ talos_dir }}/machineconfig.yaml.j2") \
    -p @<(just template "{{ talos_dir }}/nodes/{{ node }}.yaml.j2")

[doc('Reboot a node')]
reboot-node node:
  gum confirm "Reboot node {{ node }}?" && \
    talosctl -n {{ node }} reboot -m powercycle || exit 0

[doc('Reset a node')]
reset-node node mode="reboot":
  gum confirm "Reset node {{ node }}?" && \
    talosctl -n "{{ node }}" reset --system-labels-to-wipe STATE --system-labels-to-wipe EPHEMERAL --system-labels-to-wipe u-local-hostpath --graceful=false {{ if mode == "reboot" { "--reboot" } else { "" } }} || exit 0

[doc('Reset all nodes in the cluster')]
reset-cluster mode="reboot":
  just talos reset-node $(just psb talos nodes) {{ mode }}

[doc('Upgrade Kubernetes version on the cluster')]
upgrade-k8s version:
  talosctl -n "$(just psb talos controller)" upgrade-k8s --to {{ version }}

[doc('Upgrade Talos version on a node')]
upgrade-node node:
  talosctl -n "{{ node }}" upgrade -i "$(just psb talos machine-image {{ node }})" -m powercycle --timeout=10m

[doc('Download Talos machine image')]
download-image version schematic:
  gum spin --title "Downloading Talos {{ version }} ..." -- \
  curl -sfL --remove-on-error --retry 5 --retry-delay 5 --retry-all-errors \
      -o "{{ talos_dir }}/talos-{{ version }}-{{ replace_regex(schematic, '^(.{8}).*', '$1') }}.iso" \
      "https://factory.talos.dev/image/{{ schematic }}/{{ version }}/metal-amd64.iso"
  just log info "Downloaded Talos" version "{{ version }}" schematic "{{ schematic }}"

[private]
machine-controller node:
  just template "{{ talos_dir }}/nodes/{{ node }}.yaml.j2" | yq -e 'select(.machine) | (.machine.type == "controlplane") // ""'

[doc('Get the machine image for a given node')]
[private]
machine-image node:
  talosctl --nodes {{ node }} get machineconfig --output=jsonpath='{.spec}' | yq -e 'select(.machine) | .machine.install.image'

[doc('Generate talosconfig from 1Password secrets')]
gen-talosconfig:
  #!/usr/bin/env bash
  set -euo pipefail
  
  just log info "Generating talosconfig from 1Password secrets"
  
  TMPDIR=$(mktemp -d)
  trap "rm -rf ${TMPDIR}" EXIT
  
  just log info "Retrieving CA certificates from 1Password"
  op read "op://NebularGrid/6i7sewsv3lus3qxpwddknc7jem/machine ca crt" | base64 -d > "${TMPDIR}/ca.crt"
  op read "op://NebularGrid/6i7sewsv3lus3qxpwddknc7jem/machine ca key" | base64 -d > "${TMPDIR}/ca.key"
  
  just log info "Generating and signing client certificate"
  talosctl gen key --name "${TMPDIR}/admin"
  talosctl gen csr --key "${TMPDIR}/admin.key" --ip 127.0.0.1 
  talosctl gen crt --ca "${TMPDIR}/ca" --csr "${TMPDIR}/admin.csr" --name "${TMPDIR}/admin" --hours 8760
 
  CLUSTER_NAME="psb"
  
  just log info "Updating talosconfig for context: ${CLUSTER_NAME}"
  yq eval ".contexts.${CLUSTER_NAME}.ca = \"$(base64 -w0 "${TMPDIR}/ca.crt")\" | \
    .contexts.${CLUSTER_NAME}.crt = \"$(base64 -w0 "${TMPDIR}/admin.crt")\" | \
    .contexts.${CLUSTER_NAME}.key = \"$(base64 -w0 "${TMPDIR}/admin.key")\"" \
    -i {{ root }}/talosconfig
  
  just log info "Successfully updated talosconfig"

