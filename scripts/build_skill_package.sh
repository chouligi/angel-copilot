#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/skills/public/angel-copilot"
OUTPUT_PATH="${1:-$ROOT_DIR/angel-copilot.skill}"

if [[ "$OUTPUT_PATH" != /* ]]; then
  OUTPUT_PATH="$PWD/$OUTPUT_PATH"
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Source skill directory not found: $SOURCE_DIR" >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "'zip' is required but not found in PATH." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STAGE_DIR="$TMP_DIR/stage"
mkdir -p "$STAGE_DIR"
cp -R "$SOURCE_DIR"/. "$STAGE_DIR"/
find "$STAGE_DIR" -name ".DS_Store" -type f -delete

mkdir -p "$(dirname "$OUTPUT_PATH")"

(
  cd "$STAGE_DIR"
  find . -type f | LC_ALL=C sort | sed 's|^\./||' > "$TMP_DIR/file_list.txt"
  rm -f "$OUTPUT_PATH"
  zip -X -q "$OUTPUT_PATH" -@ < "$TMP_DIR/file_list.txt"
)

echo "Packaged skill written to: $OUTPUT_PATH"
