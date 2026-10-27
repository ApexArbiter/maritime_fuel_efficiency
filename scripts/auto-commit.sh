#!/usr/bin/env bash
# Snapshot this repo and push to GitHub. Local commits disappear if the
# instance disk dies, so a failed push is treated as a failure.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

mkdir -p "$REPO/.git"
LOCK="$REPO/.git/auto-commit.lock"
LOG="$REPO/.git/auto-commit.log"

exec 9>"$LOCK"
if ! flock -n 9; then
  exit 0
fi

if [[ -f "$LOG" ]] && [[ "$(stat -c%s "$LOG")" -gt 1048576 ]]; then
  tail -n 200 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-ApexArbiter}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-137857704+ApexArbiter@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "not a git repository"
    exit 1
  fi

  git add -A

  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    base="$(basename "$f")"
    case "$base" in
      .env|.env.*|credentials.json|id_rsa|id_ed25519|*.pem|*.key)
        echo "UNSTAGE secret: $f"
        git reset -q -- "$f" || true
        ;;
    esac
  done < <(git diff --cached --name-only)

  while IFS= read -r f; do
    [[ -z "$f" || ! -f "$f" ]] && continue
    size="$(stat -c%s "$f" 2>/dev/null || echo 0)"
    if [[ "$size" -gt 90000000 ]]; then
      if ! git check-attr filter -- "$f" | grep -q 'filter: lfs'; then
        echo "UNSTAGE oversized file not in Git LFS: $f ($size bytes)"
        git reset -q -- "$f" || true
      fi
    fi
  done < <(git diff --cached --name-only)

  if git diff --cached --quiet; then
    echo "clean"
    exit 0
  fi

  if ! git commit -m "auto: snapshot $(date -u +%Y-%m-%dT%H:%M:%SZ)"; then
    echo "commit failed"
    exit 1
  fi

  if git push origin HEAD; then
    echo "pushed $(git rev-parse --short HEAD)"
  else
    echo "PUSH FAILED. This snapshot is only on this machine until GitHub authentication works."
    exit 1
  fi
} >>"$LOG" 2>&1
