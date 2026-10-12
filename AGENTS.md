# AGENTS.md: using agent-board in a project

For an AI agent told to use this board to follow its sub-agents. Do these in order.

1. **Install and run.** Check: `curl -s 127.0.0.1:8120/api/state`. If it fails:
   `git clone https://github.com/plooum/agent-board ~/.local/opt/agent-board && ~/.local/opt/agent-board/install.sh`
   **Tell the user first** if `~/.claude/settings.json` already exists: the script adds a hook to that global config (it keeps everything else and writes a `.bak`). A new Claude Code session may be needed for the hook to apply. The script is idempotent; `--no-start` skips starting the server.
2. **While piloting.** Load the `agent-board` skill. Launch sub-agents with worktree isolation (the hook only follows agents in `.claude/worktrees/`). Register, archive and update their status as the skill says.
3. **Wire the project's tests (optional).** Test runners post events: README, "Plug in a test runner". Playwright runners stream the browser with `board_stream.py`: README, "Plug in a browser screencast". The project must work without the board: import in a `try`, locate it through `AGENT_BOARD_HOME`, never fail when the board is down.
4. **Tell future agents.** Add one line to the project's `CLAUDE.md` (or pilot notes): "Sub-agents are followed on the agent board (https://github.com/plooum/agent-board); load the `agent-board` skill before launching them."
5. **The user watches** at http://127.0.0.1:8120 in their own browser (project filter in the header).
