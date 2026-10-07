#!/usr/bin/env bash
#
# TeacherCopilot - one-command start for macOS and Linux.
#
#   ./run.sh            start the app on http://127.0.0.1:5173
#   ./run.sh build      produce a production build in frontend/dist
#
# The app runs entirely in your browser. No backend, no API key, no database
# and no Python are needed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
PORT="${PORT:-5173}"

blue()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }

[ -d "$FRONTEND" ] || { red "Could not find the 'frontend' folder."; exit 1; }
command -v npm >/dev/null 2>&1 || {
  red "Node.js/npm is required but was not found."
  red "Install Node.js 18 or newer from https://nodejs.org"
  exit 1
}

cd "$FRONTEND"

if [ ! -d node_modules ]; then
  blue "Installing dependencies (first run takes a minute)"
  npm install
fi

if [ "${1:-run}" = "build" ]; then
  blue "Building for production into frontend/dist"
  npm run build
  echo
  echo "To preview the production build:  cd frontend && npx vite preview"
  exit 0
fi

echo
green "TeacherCopilot -> http://127.0.0.1:$PORT"
echo
echo "  Sign in with    demo@teachercopilot.app / demo1234"
echo "  Press Ctrl+C to stop."
echo
exec npm run dev -- --port "$PORT"