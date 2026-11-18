#!/usr/bin/env bash
# Checks that the main development tools are installed.

tools=("git" "python3" "pip3" "node" "npm" "pnpm" "docker" "code")

for tool in "${tools[@]}"; do
  if command -v "$tool" > /dev/null 2>&1; then
    echo "OK       $tool  ->  $($tool --version 2>&1 | head -n 1)"
  else
    echo "MISSING  $tool"
  fi
done

echo
docker compose version 2>&1 | head -n 1
