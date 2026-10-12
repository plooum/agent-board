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

## Plug in a Claude Code hook (to come)

A `PostToolUse` hook can run `python3 board.py event <agent-id> "<command or file edited>"` (or POST the same to `/api/events`) to show the agent's actions in its timeline.
