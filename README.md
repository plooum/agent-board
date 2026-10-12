# agent-board

A small, self-contained tool: one live web page to follow coding agents (a title, a name, what each is doing now, its test runs as they happen), kept viewable after they finish. Python standard library only, no dependency, no external asset. It listens on `127.0.0.1` only.

## Run it

```bash
python3 board.py serve [--port 8120] [--data DIR]    # then open http://127.0.0.1:8120
```

Data lives in `~/.local/share/agent-board/` by default: an append-only `events.jsonl`, loaded in memory at start. Entries older than 30 days are dropped at start and once a day.

Command line client (POSTs to the server, `--url` or `AGENT_BOARD_URL`, default `http://127.0.0.1:8120`; exits 0 silently when the server is down, `-v` prints the error, so it can sit in any script):

```bash
python3 board.py agent <id> [--title T] [--name N] [--status S] [--branch B] [--pr URL] [--port P] [--checkout PATH]
python3 board.py event <id> "what the agent is doing"
python3 board.py archive --except <id> [<id>...]     # archive every other non-archived agent
```

`agent` upserts: only the given fields change. Statuses used by the page: `working`, `review`, `done`, `archived` (any text is accepted). Archived agents are collapsed in the page but stay viewable.

## HTTP API

JSON, CORS open (`Access-Control-Allow-Origin: *`), so a page served elsewhere can post.

| Request | Purpose |
| :--- | :--- |
| `POST /api/agents/<id>` | upsert an agent: `title name status branch pr port checkout` |
| `POST /api/agents/archive` | `{"except": [ids]}` |
| `POST /api/events` | `{agent?, port?, kind, text?, data?, ...}`; without `agent`, resolved from `port` (the most recently updated agent with that port; an unknown port creates the agent `port-<n>`). The server sets `ts` |
| `GET /api/state` | agents, each with its last action and last run |
| `GET /api/agents/<id>/events` | `{events, runs}` of one agent |
| `GET /api/runs?suite=` | test runs, newest first, each with its tests |
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

A finished test's picture: `page.screenshot(type="jpeg")` posted to `/api/shots?port=<port>&run=<run>&name=<test>`. `dev/board_stream.py` in this repo is a ready-made version.

## Plug in a Claude Code hook

`hook.py` is a `PostToolUse` hook that posts what an agent does to its timeline. Add to `.claude/settings.json`:

```json
{ "hooks": { "PostToolUse": [ { "matcher": "Bash|Edit|Write|NotebookEdit",
    "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/path/to/hook.py\" --only-under /.claude/worktrees/" } ] } ] } }
```

Posted as `action` events: `Bash` as its `description` (else the first line of the command, cut to 120 characters); `Edit` / `Write` / `NotebookEdit` as `Edit <path>` / `Write <path>`, the path relative to the checkout. Other tools post nothing. The agent id is the folder name of the checkout (the nearest parent holding a `.git`).

Options: `--url` (or `AGENT_BOARD_URL`, default `http://127.0.0.1:8120`); `--only-under <substring>` posts only when the checkout path contains it (here, worktrees only, so a main checkout is never posted). The hook uses a 0.5 s timeout, swallows every error, prints nothing and always exits 0.
