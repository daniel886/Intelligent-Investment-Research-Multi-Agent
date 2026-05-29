#!/usr/bin/env bash
# init_github.sh — Initialise git, commit, create remote on GitHub and push.
#
# Usage:
#   GITHUB_USER=<your-handle> GITHUB_TOKEN=<token> ./init_github.sh
#   (optional) REPO_NAME=Intelligent-Investment-Research-Multi-Agent
#   (optional) REPO_VISIBILITY=public|private (default: public)
#
# Requires: git + (gh OR curl). If `gh` (GitHub CLI) is installed and
# authenticated, it will be preferred — otherwise falls back to the REST API.

set -euo pipefail

REPO_NAME="${REPO_NAME:-Intelligent-Investment-Research-Multi-Agent}"
REPO_VISIBILITY="${REPO_VISIBILITY:-public}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

if [[ -z "${GITHUB_USER:-}" ]]; then
  echo "❌ Please export GITHUB_USER (your GitHub username/org)."
  exit 1
fi

echo "🛠  Project: $REPO_NAME"
echo "🌐 Owner:   $GITHUB_USER"
echo "🔒 Visibility: $REPO_VISIBILITY"

# 1) git init / commit -------------------------------------------------------
if [[ ! -d .git ]]; then
  git init -b "$DEFAULT_BRANCH"
fi

git add -A
git -c user.email="bot@qoder.com" -c user.name="QoderBot" \
  commit -m "feat: initial commit — multi-agent investment research system" || true

# 2) Create remote on GitHub -------------------------------------------------
REMOTE_URL=""
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "🚀 Using GitHub CLI to create repo..."
  gh repo create "$GITHUB_USER/$REPO_NAME" \
    --"$REPO_VISIBILITY" --source=. --remote=origin --push --confirm || true
  REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
else
  if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "❌ GITHUB_TOKEN is required when 'gh' CLI is not available."
    exit 1
  fi
  echo "📡 Creating repo via GitHub REST API..."
  PRIVATE_FLAG=$([[ "$REPO_VISIBILITY" == "private" ]] && echo true || echo false)
  curl -fsSL -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    https://api.github.com/user/repos \
    -d "{\"name\":\"$REPO_NAME\",\"private\":$PRIVATE_FLAG,\"auto_init\":false}" \
    | grep -E '"clone_url"|"html_url"' || true

  REMOTE_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
  git remote remove origin 2>/dev/null || true
  git remote add origin "$REMOTE_URL"
  git push -u origin "$DEFAULT_BRANCH"
fi

echo "✅ Repository pushed successfully → https://github.com/$GITHUB_USER/$REPO_NAME"
