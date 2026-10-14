---
name: agent-board
description: Load when you launch or manage sub-agents and the agent board is installed (~/.local/opt/agent-board), to show them on the board.
---

# Agent board

A live page (http://127.0.0.1:8120) showing sub-agents: title, name, status, actions, test runs, browser view.

## Is it up?

`curl -s 127.0.0.1:8120/api/state`. If it fails and the board isn't installed (no `~/.local/opt/agent-board`), run `~/.local/opt/agent-board/install.sh` (clone it first, see AGENTS.md). Otherwise start it:
`(setsid nohup python3 ~/.local/opt/agent-board/board.py serve > /dev/null 2>&1 &)`

## Register a sub-agent

The agent id is `agent-<id>`, the basename of its worktree (what the hook and test runners use). Right after launching a sub-agent in a worktree:

```bash
B=~/.local/opt/agent-board/board.py
python3 $B archive --except agent-<id>     # archives the project's other agents (only this project's)
python3 $B agent agent-<id> --title "..." --name "..." --status working --branch <branch> \
  --checkout <main checkout>/.claude/worktrees/agent-<id>
```

Then update the status:

- at review: `python3 $B agent agent-<id> --status review --pr <url>`
- after merge: `python3 $B agent agent-<id> --status done`

## Usage (plan limits, context window)

In the Claude desktop app, at each step (session start, launch, review, merge): call the app's `get_usage` tool, write its JSON output as is to a file in your scratchpad, then `python3 $B usage --file <that file>`. The board shows the 5-hour and weekly limits and your context window. Tell the user when a limit nears 80 %.

`board.py` exits 0 silently when the board is down. Actions come from the global `PostToolUse` hook; test runners report through the HTTP API and `board_stream.py` (see the README, "Plug in a test runner" and "Plug in a browser screencast").
