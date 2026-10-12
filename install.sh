#!/usr/bin/env bash
# Install agent-board: clone/pull, Claude Code hook, skill link, start the server. Idempotent.
set -euo pipefail

REPO_URL="https://github.com/plooum/agent-board"
HOME_DIR="${AGENT_BOARD_HOME:-$HOME/.local/opt/agent-board}"
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
URL="${AGENT_BOARD_URL:-http://127.0.0.1:8120}"
START=1
[ "${1:-}" = "--no-start" ] && START=0

# 1. clone or pull
if [ -d "$HOME_DIR/.git" ]; then
  git -C "$HOME_DIR" pull --ff-only -q && echo "pull: $HOME_DIR"
else
  mkdir -p "$(dirname "$HOME_DIR")"
  git clone -q "$REPO_URL" "$HOME_DIR" && echo "clone: $HOME_DIR"
fi
HOME_DIR="$(cd "$HOME_DIR" && pwd)"

# 2. hook
mkdir -p "$(dirname "$SETTINGS")"
python3 - "$SETTINGS" "$HOME_DIR" <<'PY'
import json, os, shutil, sys
path, home = sys.argv[1], sys.argv[2]
exists = os.path.exists(path)
data = {}
if exists:
    try:
        with open(path) as f:
            data = json.load(f)
    except ValueError as e:
        sys.exit("hook: %s is not valid JSON (%s); nothing changed" % (path, e))
    if not isinstance(data, dict):
        sys.exit("hook: %s is not a JSON object; nothing changed" % path)
hooks = data.get("hooks")
if hooks is not None and not isinstance(hooks, dict):
    sys.exit("hook: 'hooks' in %s is not an object; nothing changed" % path)
post = (hooks or {}).get("PostToolUse", [])
if "agent-board/hook.py" in json.dumps(post):
    print("hook already there")
    sys.exit(0)
entry = {"matcher": "Bash|Edit|Write|NotebookEdit", "hooks": [{
    "type": "command",
    "command": "python3 %s/hook.py --only-under /.claude/worktrees/" % home}]}
if exists:
    shutil.copy2(path, path + ".bak")
data.setdefault("hooks", {}).setdefault("PostToolUse", []).append(entry)
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print("hook added" + (" (backup: %s.bak)" % path if exists else " (created %s)" % path))
PY

# 3. skill
SKILL_DIR="$HOME/.claude/skills"; LINK="$SKILL_DIR/agent-board"
mkdir -p "$SKILL_DIR"
if [ -L "$LINK" ] && [ "$(readlink "$LINK")" = "$HOME_DIR/skill" ]; then
  echo "skill already there"
elif [ -e "$LINK" ] || [ -L "$LINK" ]; then
  echo "skill left alone: $LINK already exists and is not our link (warning)"
else
  ln -s "$HOME_DIR/skill" "$LINK" && echo "skill linked"
fi

# 4. server
if [ "$START" = 0 ]; then
  echo "board skipped (--no-start)"
elif curl -s -m 2 "$URL/api/state" > /dev/null 2>&1; then
  echo "board already running"
else
  (setsid nohup python3 "$HOME_DIR/board.py" serve > /dev/null 2>&1 &)
  sleep 1
  echo "board started"
fi
echo "Open $URL"
