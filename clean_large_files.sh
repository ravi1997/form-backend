#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="main"
BACKUP_BRANCH="${BRANCH}-backup"

REMOVE_PATHS=(
  "lora/llama-factory-output"
  ".codebase-memory"
)

IGNORE_PATTERNS=(
  "lora/llama-factory-output/"
  ".codebase-memory/"
  "*.pt"
  "*.safetensors"
  "*.zst"
)

echo "=== Git History Cleanup ==="

# Ensure we're inside a git repo
git rev-parse --is-inside-work-tree >/dev/null

# Create backup branch if needed
if git show-ref --verify --quiet "refs/heads/${BACKUP_BRANCH}"; then
    echo "Backup branch '${BACKUP_BRANCH}' already exists."
else
    echo "Creating backup branch '${BACKUP_BRANCH}'..."
    git branch "${BACKUP_BRANCH}"
fi

# Switch to target branch
git checkout "${BRANCH}"

# Stash local changes if present
STASH_CREATED=0
if ! git diff --quiet || ! git diff --cached --quiet || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    echo "Stashing local changes..."
    git stash push -u -m "pre-filter-repo-backup"
    STASH_CREATED=1
fi

# Verify git-filter-repo exists
if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo
    echo "ERROR: git-filter-repo is not installed."
    echo
    echo "Install one of:"
    echo "  sudo apt install git-filter-repo"
    echo "or"
    echo "  pipx install git-filter-repo"
    exit 1
fi

# Build filter-repo arguments
REMOVE_ARGS=()
for path in "${REMOVE_PATHS[@]}"; do
    REMOVE_ARGS+=(--path "$path")
done

echo "Removing paths from repository history..."
git filter-repo "${REMOVE_ARGS[@]}" --invert-paths --force

# Ensure .gitignore contains ignore patterns
touch .gitignore

for pattern in "${IGNORE_PATTERNS[@]}"; do
    grep -qxF "$pattern" .gitignore || echo "$pattern" >> .gitignore
done

if ! git diff --quiet .gitignore; then
    git add .gitignore
    git commit -m "chore: ignore generated training artifacts"
fi

# Clean corrupt temporary object if present
find .git/objects -type f -name 'tmp_obj_*' -delete 2>/dev/null || true

echo "Running git gc..."
git gc --prune=now --aggressive

echo
echo "Repository size after cleanup:"
git count-objects -vH

# Restore stash if one was created
if [[ $STASH_CREATED -eq 1 ]]; then
    echo
    echo "Restoring stashed changes..."
    git stash pop || true
fi

echo
echo "Review repository status before pushing:"
git status

echo
echo "When satisfied, push with:"
echo
echo "  git push --force-with-lease origin ${BRANCH}"
echo
echo "Backup branch available at: ${BACKUP_BRANCH}"