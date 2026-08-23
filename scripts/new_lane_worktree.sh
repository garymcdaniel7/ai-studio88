#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <lane>" >&2
  exit 2
fi

lane="$1"
if [[ ! "$lane" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "invalid lane: $lane" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
worktree_path="${repo_root}/../ai-studio88-${lane}"
branch="agent/${lane}"

if [[ -e "$worktree_path" || -L "$worktree_path" ]]; then
  echo "worktree path already exists: $worktree_path" >&2
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/${branch}"; then
  echo "branch already exists: $branch" >&2
  exit 1
fi

git worktree add -b "$branch" "$worktree_path" HEAD >/dev/null
printf '%s\n' "$worktree_path"
