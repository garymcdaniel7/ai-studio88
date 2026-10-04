#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Build detector fragments without putting complete credential prefixes in this file.
OPENAI_PREFIX='s''k-'
HF_PREFIX='h''f_'
JWT_PREFIX='e''yJ'
PRIVATE_HEADER='-----BEGIN '"PRIVATE"' KEY-----'
B2_PREFIX='B2''_'

PATTERNS=(
  "${OPENAI_PREFIX}[A-Za-z0-9]{20,}"
  "${HF_PREFIX}[A-Za-z0-9]{20,}"
  "${JWT_PREFIX}[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{10,}\\."
  "${PRIVATE_HEADER}"
  "${B2_PREFIX}(KEY_ID|APPLICATION_KEY)[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9_-]{12,}"
  '\"(keyId|applicationKey)\"[[:space:]]*:[[:space:]]*\"[^\"]{12,}\"'
)

is_excluded_path() {
  case "$1" in
    .env|.env.*|*/.env|*/.env.*|*/node_modules/*|*/.next/*|*/coverage/*|*/test-results/*|*/playwright-report/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_source_path() {
  case "$1" in
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.sh|*.py|*.css|*.scss|*.html|*.md|*.yml|*.yaml)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

files=()
if (( $# > 0 )); then
  files=("$@")
else
  while IFS= read -r file; do
    files+=("$file")
  done < <(
    {
      git -C "$REPO_ROOT" ls-files -- frontend
      git -C "$REPO_ROOT" ls-files --others --exclude-standard -- frontend
    } | sort -u
  )
fi

checked=0
found=0
for file in "${files[@]}"; do
  if is_excluded_path "$file" || ! is_source_path "$file"; then
    continue
  fi

  if [[ "$file" = /* ]]; then
    absolute_path="$file"
    display_path="$file"
  else
    absolute_path="$REPO_ROOT/$file"
    display_path="$file"
  fi

  if [[ ! -f "$absolute_path" ]] || ! grep -Iq . "$absolute_path"; then
    continue
  fi

  checked=$((checked + 1))
  for pattern in "${PATTERNS[@]}"; do
    if grep -qE -- "$pattern" "$absolute_path"; then
      printf 'Potential credential pattern detected in %s\n' "$display_path" >&2
      found=1
      break
    fi
  done
done

if (( found != 0 )); then
  printf 'Secret scan failed; matched files are listed without exposing content.\n' >&2
  exit 1
fi

printf 'Secret scan passed (%d source files checked).\n' "$checked"
