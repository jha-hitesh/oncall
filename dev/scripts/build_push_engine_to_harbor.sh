#!/usr/bin/env bash

set -euo pipefail

readonly IMAGE_REPOSITORY="harbor-core.fynd.engineering/common/gofynd/sre/oncall"
readonly PLATFORM="linux/amd64"

usage() {
  cat <<'EOF'
Usage: scripts/build-and-push-image.sh <tag>

Builds the local Docker image for linux/amd64, tags it, pushes it,
and removes the pushed tag from the local machine.
EOF
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
fi

tag="$1"
tag="${tag#v}"

if [[ -z "$tag" ]]; then
  echo "Error: tag must not be empty." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is required but was not found in PATH." >&2
  exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
  echo "Error: docker buildx is required but is not available." >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
engine_dir="${repo_root}/engine"
image_ref="${IMAGE_REPOSITORY}:${tag}"

echo "Building ${image_ref} for ${PLATFORM} from Dockerfile ${engine_dir}..."
docker buildx build \
  --platform "${PLATFORM}" \
  --file "${engine_dir}/Dockerfile" \
  --tag "${image_ref}" \
  --load \
  "${engine_dir}"

echo "Pushing ${image_ref}..."
docker push "${image_ref}"

echo "Removing local tag ${image_ref}..."
docker image rm "${image_ref}"

echo "Done."
