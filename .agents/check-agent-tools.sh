#!/usr/bin/env bash
set -euo pipefail

required=(
  node
  npm
  npx
  uv
  uvx
  git
  rg
  jq
  docker
)

for cmd in "${required[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing: $cmd"
    exit 1
  fi
done

python_tools=(
  mcp-server-git
  mcp-server-fetch
  mcp-server-time
)

for cmd in "${python_tools[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing python MCP tool: $cmd"
    echo "install with: uv tool install $cmd"
    exit 1
  fi
done

npm view @modelcontextprotocol/server-filesystem version >/dev/null
npm view @modelcontextprotocol/server-memory version >/dev/null
npm view @modelcontextprotocol/server-sequential-thinking version >/dev/null
npm view @playwright/mcp version >/dev/null
npm view @upstash/context7-mcp version >/dev/null
npm view chrome-devtools-mcp version >/dev/null

if ! find "$HOME/.cache/ms-playwright" -maxdepth 1 -type d -name 'chromium*' 2>/dev/null | grep -q .; then
  echo "missing Playwright Chromium browser cache"
  echo "install with: npx -y playwright install chromium"
  exit 1
fi

if ! docker image inspect ghcr.io/github/github-mcp-server >/dev/null 2>&1; then
  echo "GitHub MCP image not cached; first use will pull ghcr.io/github/github-mcp-server"
fi

if [ ! -r "$HOME/.config/ridp-agent/github-mcp.env" ]; then
  echo "missing GitHub MCP env file: $HOME/.config/ridp-agent/github-mcp.env"
  echo "create it with owner-only permissions and GITHUB_PERSONAL_ACCESS_TOKEN"
elif [ "$(stat -c '%a' "$HOME/.config/ridp-agent/github-mcp.env")" != "600" ]; then
  echo "GitHub MCP env file should be chmod 600"
fi

python3 -m json.tool .mcp.json >/dev/null

echo "agent tooling ok"
