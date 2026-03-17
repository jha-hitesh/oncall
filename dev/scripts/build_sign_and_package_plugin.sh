#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PLUGIN_DIR="${REPO_ROOT}/grafana-plugin"
ARTIFACTS_DIR="${REPO_ROOT}/dev/artifacts"

usage() {
  cat <<'EOF'
Usage: dev/scripts/build_sign_and_package_plugin.sh <plugin_version>

Example:
  dev/scripts/build_sign_and_package_plugin.sh v1.2.3

Notes:
  - A leading "v" is stripped to match the GitHub Action behavior.
  - The script expects jq, pnpm, zip, and mage to be installed.
  - Plugin signing credentials must already be available in your environment.
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required command not found: $cmd" >&2
    exit 1
  fi
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

PLUGIN_VERSION_NUMBER="$1"
PLUGIN_VERSION="${PLUGIN_VERSION_NUMBER#v}"
ARTIFACT_FILENAME="grafana-oncall-app-${PLUGIN_VERSION}.zip"

require_cmd jq
require_cmd pnpm
require_cmd zip
require_cmd mage

mkdir -p "${ARTIFACTS_DIR}"

cd "${PLUGIN_DIR}"

if [[ ! -x node_modules/.bin/webpack ]]; then
  echo "Frontend dependencies are missing in ${PLUGIN_DIR}/node_modules." >&2
  echo "Run: (cd ${PLUGIN_DIR} && pnpm install)" >&2
  exit 1
fi

PACKAGE_JSON_BACKUP="$(mktemp)"
cp package.json "${PACKAGE_JSON_BACKUP}"

cleanup() {
  cp "${PACKAGE_JSON_BACKUP}" package.json
  rm -f "${PACKAGE_JSON_BACKUP}"
}

trap cleanup EXIT

echo "Building plugin version: ${PLUGIN_VERSION}"

jq --arg v "${PLUGIN_VERSION}" '.version=$v' package.json > package.new
mv package.new package.json
jq '.version' package.json

pnpm build

if ! mage buildAll; then
  echo "mage buildAll failed; continuing to match CI behavior" >&2
fi

SIGN_STATUS="signed"
if ! pnpm sign; then
  SIGN_STATUS="unsigned"
  echo "Plugin signing failed; continuing to package an unsigned build." >&2
fi

if [[ ! -d dist ]]; then
  echo "Build output directory dist was not created, aborting." >&2
  exit 1
fi

if [[ ! -f dist/MANIFEST.txt ]]; then
  SIGN_STATUS="unsigned"
  echo "MANIFEST.txt not found; packaging an unsigned build." >&2
fi

PACKAGE_DIR="grafana-oncall-app"
ZIP_PATH="${ARTIFACTS_DIR}/${ARTIFACT_FILENAME}"

rm -rf "${PACKAGE_DIR}" "${ZIP_PATH}"
cp -R dist "${PACKAGE_DIR}"
zip -rq "${ZIP_PATH}" "./${PACKAGE_DIR}"
rm -rf "${PACKAGE_DIR}"

echo "Created ${SIGN_STATUS} artifact: ${ZIP_PATH}"
