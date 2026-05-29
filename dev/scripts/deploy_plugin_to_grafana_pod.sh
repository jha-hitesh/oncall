#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_ARTIFACT_DIR="${REPO_ROOT}/dev/artifacts"
DEFAULT_NAMESPACE="utility"
DEFAULT_POD_SELECTOR="utility-oncall-grafana"
PLUGIN_DIR="/var/lib/grafana/plugins"
PLUGIN_NAME="grafana-oncall-app"
RESTART_POD=false

usage() {
  cat <<'EOF'
Usage: dev/scripts/deploy_plugin_to_grafana_pod.sh [--restart-pod] [zip_path] [namespace] [pod_name]

Examples:
  dev/scripts/deploy_plugin_to_grafana_pod.sh
  dev/scripts/deploy_plugin_to_grafana_pod.sh --restart-pod
  dev/scripts/deploy_plugin_to_grafana_pod.sh dev/artifacts/grafana-oncall-app-2.0.0-rc5.zip
  dev/scripts/deploy_plugin_to_grafana_pod.sh --restart-pod dev/artifacts/grafana-oncall-app-2.0.0-rc5.zip
  dev/scripts/deploy_plugin_to_grafana_pod.sh dev/artifacts/grafana-oncall-app-2.0.0-rc5.zip utility utility-oncall-grafana-abc123

Behavior:
  - Copies the zip into the Grafana pod
  - Replaces /var/lib/grafana/plugins/grafana-oncall-app
  - Either reloads the backend plugin process or restarts the Grafana pod
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required command not found: $cmd" >&2
    exit 1
  fi
}

resolve_latest_artifact() {
  local latest
  latest="$(find "${DEFAULT_ARTIFACT_DIR}" -maxdepth 1 -type f -name 'grafana-oncall-app-*.zip' | sort | tail -n 1)"
  if [[ -z "${latest}" ]]; then
    echo "No plugin zip found in ${DEFAULT_ARTIFACT_DIR}" >&2
    exit 1
  fi
  echo "${latest}"
}

resolve_pod() {
  local namespace="$1"
  local pod_name="${2:-}"

  if [[ -n "${pod_name}" ]]; then
    echo "${pod_name}"
    return
  fi

  kubectl get pods -n "${namespace}" -o name \
    | grep "${DEFAULT_POD_SELECTOR}" \
    | head -n 1 \
    | cut -d/ -f2
}

wait_for_replacement_pod() {
  local namespace="$1"
  local old_pod_name="$2"
  local new_pod_name=""

  echo "Waiting for replacement pod in namespace ${namespace}..."

  for _ in $(seq 1 60); do
    new_pod_name="$(resolve_pod "${namespace}")"
    if [[ -n "${new_pod_name}" && "${new_pod_name}" != "${old_pod_name}" ]]; then
      break
    fi
    sleep 2
  done

  if [[ -z "${new_pod_name}" || "${new_pod_name}" == "${old_pod_name}" ]]; then
    echo "Timed out waiting for replacement Grafana pod in namespace ${namespace}" >&2
    exit 1
  fi

  echo "Waiting for pod to become Ready: ${new_pod_name}"
  kubectl wait --for=condition=Ready "pod/${new_pod_name}" -n "${namespace}" --timeout=180s >/dev/null
  echo "Grafana pod restarted successfully: ${new_pod_name}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --restart-pod)
      RESTART_POD=true
      shift
      ;;
    *)
      break
      ;;
  esac
done

require_cmd kubectl
require_cmd unzip

ZIP_PATH="${1:-$(resolve_latest_artifact)}"
NAMESPACE="${2:-${DEFAULT_NAMESPACE}}"
POD_NAME="$(resolve_pod "${NAMESPACE}" "${3:-}")"

if [[ ! -f "${ZIP_PATH}" ]]; then
  echo "Zip not found: ${ZIP_PATH}" >&2
  exit 1
fi

if [[ -z "${POD_NAME}" ]]; then
  echo "No Grafana pod matching ${DEFAULT_POD_SELECTOR} found in namespace ${NAMESPACE}" >&2
  exit 1
fi

ZIP_BASENAME="$(basename "${ZIP_PATH}")"
REMOTE_ZIP="/tmp/${ZIP_BASENAME}"

echo "Using pod: ${POD_NAME}"
echo "Using zip: ${ZIP_PATH}"

kubectl cp "${ZIP_PATH}" "${NAMESPACE}/${POD_NAME}:${REMOTE_ZIP}" -n "${NAMESPACE}"

kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- sh -lc "
  set -e
  cd '${PLUGIN_DIR}'
  if [ ! -d '${PLUGIN_NAME}' ] && [ -d '${PLUGIN_NAME}.prev' ]; then
    mv '${PLUGIN_NAME}.prev' '${PLUGIN_NAME}'
  fi
  rm -rf '${PLUGIN_NAME}.prev'
  mv '${PLUGIN_NAME}' '${PLUGIN_NAME}.prev'
  unzip -qo '${REMOTE_ZIP}' -d '${PLUGIN_DIR}'
  grep -n '\"version\"' '${PLUGIN_DIR}/${PLUGIN_NAME}/plugin.json' | head -n 1
"

if [[ "${RESTART_POD}" == "true" ]]; then
  echo "Restarting Grafana pod: ${POD_NAME}"
  kubectl delete pod -n "${NAMESPACE}" "${POD_NAME}" >/dev/null
  wait_for_replacement_pod "${NAMESPACE}" "${POD_NAME}"
  echo "Plugin deploy completed with Grafana pod restart."
  exit 0
fi

OLD_PID="$(kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- sh -lc "ps aux | grep gpx_grafana | grep -v grep | awk 'NR==1 {print \$1}'")"

if [[ -n "${OLD_PID}" ]]; then
  echo "Reloading backend plugin process: ${OLD_PID}"
  kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- sh -lc "kill '${OLD_PID}'"
  sleep 5
fi

NEW_PROCESS="$(kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- sh -lc "ps aux | grep gpx_grafana | grep -v grep || true")"

if [[ -z "${NEW_PROCESS}" ]]; then
  echo "Backend plugin process did not restart automatically." >&2
  exit 1
fi

echo "${NEW_PROCESS}"
echo "Plugin deploy and reload completed."
