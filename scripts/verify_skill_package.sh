#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/skills/public/angel-copilot"
PACKAGE_PATH="${1:-$ROOT_DIR/angel-copilot.skill}"

if [[ "$PACKAGE_PATH" != /* ]]; then
  PACKAGE_PATH="$PWD/$PACKAGE_PATH"
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Source skill directory not found: $SOURCE_DIR" >&2
  exit 1
fi

if [[ ! -f "$PACKAGE_PATH" ]]; then
  echo "Packaged skill file not found: $PACKAGE_PATH" >&2
  echo "Run ./scripts/build_skill_package.sh first." >&2
  exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
  echo "'unzip' is required but not found in PATH." >&2
  exit 1
fi

if ! command -v shasum >/dev/null 2>&1; then
  echo "'shasum' is required but not found in PATH." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

EXTRACT_DIR="$TMP_DIR/extracted"
mkdir -p "$EXTRACT_DIR"
unzip -qq "$PACKAGE_PATH" -d "$EXTRACT_DIR"
find "$EXTRACT_DIR" -name ".DS_Store" -type f -delete

build_manifest() {
  local target_dir="$1"
  local output_file="$2"

  (
    cd "$target_dir"
    find . -type f | LC_ALL=C sort | while IFS= read -r rel; do
      rel="${rel#./}"
      hash_value="$(shasum -a 256 "$rel" | awk '{print $1}')"
      printf '%s  %s\n' "$hash_value" "$rel"
    done > "$output_file"
  )
}

SOURCE_MANIFEST="$TMP_DIR/source_manifest.txt"
PACKAGE_MANIFEST="$TMP_DIR/package_manifest.txt"

build_manifest "$SOURCE_DIR" "$SOURCE_MANIFEST"
build_manifest "$EXTRACT_DIR" "$PACKAGE_MANIFEST"

if ! diff -u "$SOURCE_MANIFEST" "$PACKAGE_MANIFEST" >/dev/null; then
  echo "Skill package is out of sync with source files." >&2
  diff -u "$SOURCE_MANIFEST" "$PACKAGE_MANIFEST" || true
  echo "" >&2
  echo "Fix by running: ./scripts/build_skill_package.sh" >&2
  exit 1
fi

echo "Skill package is in sync: $PACKAGE_PATH"
