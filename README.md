# agent-board

AI agent asked to use this board: read [AGENTS.md](AGENTS.md).

Follow Claude Code sub-agents (or any coding agents) live: what each is doing, its test runs as they happen, and a live view of its headless browser; a strip above shows the plan limits (5-hour, weekly) and the pilot's context window, as last sent by the pilot. One web page, kept viewable after the agents finish. Python standard library only, no dependency, no external asset. It listens on `127.0.0.1` only.

## Install

Once per machine, one command (clones to `~/.local/opt/agent-board`, adds the Claude Code hook to `~/.claude/settings.json` without touching anything else, links the skill, starts the board; idempotent; `--no-start` skips the start; `AGENT_BOARD_HOME` and `CLAUDE_SETTINGS` override the paths):

```bash
git clone https://github.com/plooum/agent-board ~/.local/opt/agent-board && ~/.local/opt/agent-board/install.sh    # then open http://127.0.0.1:8120
```

### Manual install

```bash
git clone https://github.com/plooum/agent-board ~/.local/opt/agent-board
(setsid nohup python3 ~/.local/opt/agent-board/board.py serve > /dev/null 2>&1 &)    # then open http://127.0.0.1:8120
```

Update: `git -C ~/.local/opt/agent-board pull`, then restart the server:

```bash
kill $(ps -eo pid,args | awk '/agent-board\/board.py serve/ && !/awk/ && !/bash/ {print $1}')
(setsid nohup python3 ~/.local/opt/agent-board/board.py serve > /dev/null 2>&1 &)
```

Run the kill as a command of its own (`pkill -f` / `pgrep -f` would match the calling shell).

Clients talk to `http://127.0.0.1:8120` by default; set `AGENT_BOARD_URL` to use another board.

For Claude Code, also install the [hook](#plug-in-a-claude-code-hook) and the global skill (below).

### Claude Code skill

`skill/SKILL.md` teaches Claude Code how to register the sub-agents it launches on the board:

```bash
mkdir -p ~/.claude/skills && ln -s ~/.local/opt/agent-board/skill ~/.claude/skills/agent-board
```

## Run it

```bash
python3 board.py serve [--port 8120] [--data DIR]    # then open http://127.0.0.1:8120
```

Data lives in `~/.local/share/agent-board/` by default: an append-only `events.jsonl`, loaded in memory at start. Entries older than 30 days are dropped at start and once a day.

Command line client (POSTs to the server, `--url` or `AGENT_BOARD_URL`, default `http://127.0.0.1:8120`; exits 0 silently when the server is down, `-v` prints the error, so it can sit in any script):

```bash
python3 board.py agent <id> [--title T] [--name N] [--status S] [--branch B] [--pr URL] [--port P] [--checkout PATH] [--project P]
python3 board.py event <id> "what the agent is doing"
python3 board.py archive --except <id> [<id>...] [--project P | --all-projects]   # archive every other non-archived agent of the project
python3 board.py usage [--file F]   # plan limits + context window, JSON from F or stdin (the Claude desktop app's get_usage output)
python3 board.py pilot --status busy|waiting|idle [--waiting "what it waits for"]   # the current directory's project pilot
```

`pilot` sets the line of the current directory's project pilot under the limits strip: its state (`waiting` is highlighted with what it waits for from the user) and the context window of its last `usage` reading (a reading's `context` goes to its `project`'s pilot). Kept in `pilots.json`; no command history.

`usage` takes the JSON the Claude desktop app's `get_usage` tool returns (`plan.windows[]`: `label`, `percentUsed`, `resetsAt`; `context`: `tokensUsed`, `contextWindow`, `percentUsed`, `autoCompactsAtPercent`; either may have a `status` other than `ok`). Only the latest reading is kept (`usage.json` in the data dir). The page shows one gauge per window with the time left until `resetsAt`, a `Context` gauge with a mark at the auto-compact threshold, and the reading's age; gauges turn orange from 80 % and red from 95 % (of the threshold, for the context). Claude Code's status line would be the natural source, but it doesn't run in the desktop app.

`agent` upserts: only the given fields change. Statuses used by the page: `working`, `review`, `done`, `archived` (any text is accepted). Archived agents are collapsed in the page but stay viewable. The page's **Archive inactive** button archives, in one click, the agents of the selected project that are neither `working` nor `review`.

## HTTP API

JSON, CORS open (`Access-Control-Allow-Origin: *`), so a page served elsewhere can post.

| Request | Purpose |
| :--- | :--- |
| `POST /api/agents/<id>` | upsert an agent: `title name status branch pr port checkout project` |
| `POST /api/agents/archive` | `{"except": [ids], "project"?}`; with `project`, only that project's agents |
| `POST /api/events` | `{agent?, port?, kind, text?, data?, ...}`; without `agent`, resolved from `port` (the most recently updated agent with that port, among the event's `project` when it has one; an unknown port creates the agent `port-<n>`). The server sets `ts` |
| `GET /api/state` | agents, each with its last action and last run, and `usage` (the latest reading, or null) |
| `POST /api/pilot` | `{project, status?, waiting?, context?}`: upserts that project's pilot line; broadcast as `{type: 'pilots', pilots}`; `/api/state` returns `pilots` |
| `POST /api/usage` | the plan limits / context reading (see `board.py usage`); kept, then broadcast as `{type: 'usage', usage}` |
| `GET /api/agents/<id>/events` | `{events, runs}` of one agent |
| `GET /api/runs?suite=&project=` | test runs, newest first, each with its tests |
| `POST /api/frame?agent=\|port=` | body: a JPEG (`Content-Type: image/jpeg`). Keeps only the latest frame per agent, in memory (never stored); broadcasts `{type: 'frame', agent, ts}` over the stream, at most ~4 per second per agent |
| `GET /api/agents/<id>/frame` | the latest JPEG of an agent (404 if none), `no-store` |
| `POST /api/shots?agent=\|port=&run=&name=` | body: a JPEG. Saved as `shots/<id>.jpg` in the data dir and attached (`shot` field) to the test `name` of run `run`, whether it arrives before or after `test-end`. Pruned after 30 days like events |
| `GET /api/shots/<id>.jpg` | a saved screenshot |
| `GET /api/stream` | Server-Sent Events: a message on every new event or agent change |

Event kinds:

| `kind` | fields |
| :--- | :--- |
| `action` | `text` |
| `status` | `text` (posted by the server when an agent's status changes) |
| `run-start` | `run`, `suite`, `source`, `total` |
| `test-start` | `run`, `name` |
| `test-end` | `run`, `name`, `ok`, `seconds`, `message?` |
| `run-end` | `run`, `summary`, `passed`, `failed` |

`run` is an id chosen by whoever posts (any string, unique per run).

## Plug in a test runner

At the start of a run, for each test, and at the end, post the events above, fire and forget, so a board that is down never slows or fails the runner:

```js
const report = (kind, data) =>
  fetch('http://127.0.0.1:8120/api/events', {
    method: 'POST', keepalive: true, headers: { 'Content-Type': 'text/plain' },
    body: JSON.stringify({ kind, run, port: location.port, source: 'pane', ...data }),
  }).catch(() => {});
report('run-start', { suite: 'smoke', total: 9 });
```

Register the agent once with its `--port`, and events that carry only a `port` land on it.

## Plug in a browser screencast

The page shows a read-only live view of each agent's browser (a Browser panel above the test run) and a thumbnail per test that has a shot. With Playwright and headless Chrome, open a CDP session and post the latest frame:

```python
cdp = page.context.new_cdp_session(page)
cdp.on("Page.screencastFrame", lambda ev: (cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}), post_latest(base64.b64decode(ev["data"]))))
cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": 1280, "maxHeight": 900})
# post_latest: POST the JPEG to /api/frame?port=<port>, from a background thread that drops older frames
```

A finished test's picture: `page.screenshot(type="jpeg")` posted to `/api/shots?port=<port>&run=<run>&name=<test>`. `board_stream.py`, next to this README, is a ready-made version (it needs only the Playwright objects you pass in).

## Several projects

An agent belongs to a **project**: the absolute path of its main checkout (for a git worktree, the checkout it was made from), shown by its basename. `board.py agent` takes `--project P` and defaults to the project of `--checkout`, else of the current directory (none outside a git checkout). The hook sends it with each action. Agents without one (older data) show under "All projects".

- `archive --except ...` archives only the agents of the same project (the current directory's, or `--project P`); `--all-projects` archives across projects.
- An event resolved by `port` picks among the agents of the event's `project` when it has one.
- The page has a **Project** select in its header (remembered in the browser) that filters the agents, the archived ones and the Tests tab.

## Plug in a Claude Code hook

`hook.py` is a `PostToolUse` hook that posts what an agent does to its timeline. Declare it **once for all projects** in `~/.claude/settings.json` (merge it into the existing `hooks` if the file has some):

```json
{ "hooks": { "PostToolUse": [ { "matcher": "Bash|Edit|Write|NotebookEdit",
    "hooks": [ { "type": "command", "command": "python3 ~/.local/opt/agent-board/hook.py --only-under /.claude/worktrees/" } ] } ] } }
```

`--only-under <substring>` posts only when the agent's checkout path contains the substring: with `/.claude/worktrees/`, only agents working in Claude Code worktrees are shown, so the main session isn't.

Or per project, in its `.claude/settings.json`, with the same JSON and the path of `hook.py` (e.g. `"$CLAUDE_PROJECT_DIR/path/to/hook.py"`). Don't declare both, or actions are posted twice.

Posted as `action` events: `Bash` as its `description` (else the first line of the command, cut to 120 characters); `Edit` / `Write` / `NotebookEdit` as `Edit <path>` / `Write <path>`, the path relative to the checkout. Other tools post nothing. The agent id is the folder name of the checkout (the nearest parent holding a `.git`).

Options: `--url` (or `AGENT_BOARD_URL`, default `http://127.0.0.1:8120`); `--only-under <substring>` as above. The hook uses a 0.5 s timeout, swallows every error, prints nothing and always exits 0.
