#!/usr/bin/env python3
"""agent-board: a central, live page to follow coding agents and their test runs.

Python standard library only. Usage:

    board.py serve [--port 8120] [--data DIR]
    board.py agent <id> [--title T] [--name N] [--status S] [--branch B] [--pr URL] [--port P] [--checkout PATH]
    board.py event <id> <text>
    board.py archive --except <id>...

The client commands POST to the server (--url, env AGENT_BOARD_URL, default http://127.0.0.1:8120)
and exit 0 silently when it is not running (-v prints the error). See README.md.
"""
import argparse
import json
import os
import queue
import re
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RETENTION = 30 * 24 * 3600
AGENT_FIELDS = ('title', 'name', 'status', 'branch', 'pr', 'port', 'checkout')
DEFAULT_URL = 'http://127.0.0.1:8120'


class Store:
    """In-memory state rebuilt from the append-only events.jsonl."""

    def __init__(self, data_dir):
        self.dir = Path(data_dir).expanduser()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / 'events.jsonl'
        self.lock = threading.RLock()
        self.agents = {}
        self.events = []  # every event except agent upserts, in order
        self.runs = {}  # run id -> run record
        self.listeners = []
        self.frames = {}  # agent id -> (jpeg bytes, ts): the latest live frame only, never stored
        self.frame_sent = {}  # agent id -> time of the last 'frame' broadcast (throttle)
        self.shots_dir = self.dir / 'shots'
        self.shots_dir.mkdir(exist_ok=True)
        self.load()

    # ---- persistence -------------------------------------------------
    def load(self):
        cutoff = time.time() - RETENTION
        if self.file.exists():
            for line in self.file.read_text(encoding='utf-8').splitlines():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get('ts', 0) >= cutoff:
                    self.apply(ev)
        self.rewrite()

    def rewrite(self):
        """Drop what is older than the retention; keep a snapshot of every surviving agent."""
        with self.lock:
            cutoff = time.time() - RETENTION
            self.events = [e for e in self.events if e['ts'] >= cutoff]
            keep = {e.get('agent') for e in self.events}
            self.agents = {k: a for k, a in self.agents.items() if a['updated'] >= cutoff or k in keep}
            self.runs = {k: r for k, r in self.runs.items() if r['ts'] >= cutoff}
            lines = [json.dumps({'kind': 'agent', 'agent': a['id'], 'ts': a['updated'], 'fields': {f: a[f] for f in AGENT_FIELDS if a.get(f) is not None}, 'created': a['created']}) for a in self.agents.values()]
            lines += [json.dumps(e) for e in self.events]
            for f in self.shots_dir.glob('*.jpg'):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                except OSError:
                    pass
            tmp = self.file.with_suffix('.tmp')
            tmp.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
            tmp.replace(self.file)

    def append(self, ev):
        with self.lock:
            with self.file.open('a', encoding='utf-8') as f:
                f.write(json.dumps(ev) + '\n')

    # ---- state -------------------------------------------------------
    def touch(self, agent_id, ts):
        a = self.agents.get(agent_id)
        if a is None:
            a = self.agents[agent_id] = {'id': agent_id, 'status': 'working', 'created': ts, 'updated': ts}
        a['updated'] = max(a['updated'], ts)
        return a

    def apply(self, ev):
        """Applies one event to the in-memory state (also used to replay the file)."""
        kind, ts = ev['kind'], ev['ts']
        a = self.touch(ev['agent'], ts)
        if kind == 'agent':
            a['created'] = min(a['created'], ev.get('created', ts))
            a.update(ev['fields'])
            return
        self.events.append(ev)
        if kind == 'status':
            a['status'] = ev['text']
        elif kind == 'run-start':
            self.runs[ev['run']] = {'run': ev['run'], 'agent': ev['agent'], 'suite': ev.get('suite'), 'source': ev.get('source'),
                                    'total': ev.get('total'), 'ts': ts, 'end': None, 'summary': None, 'passed': None, 'failed': None, 'tests': []}
        elif kind in ('test-start', 'test-end', 'run-end', 'shot'):
            r = self.runs.get(ev['run'])
            if r is None:
                r = self.runs[ev['run']] = {'run': ev['run'], 'agent': ev['agent'], 'suite': ev.get('suite'), 'source': None,
                                            'total': None, 'ts': ts, 'end': None, 'summary': None, 'passed': None, 'failed': None, 'tests': []}
            if kind == 'run-end':
                r.update(end=ts, summary=ev.get('summary'), passed=ev.get('passed'), failed=ev.get('failed'))
            else:
                t = next((t for t in r['tests'] if t['name'] == ev['name']), None)
                if t is None:
                    t = {'name': ev['name'], 'start': ts, 'ok': None}
                    r['tests'].append(t)
                if kind == 'shot':
                    t['shot'] = ev['shot']
                if kind == 'test-end':
                    t.update(ok=bool(ev.get('ok')), seconds=ev.get('seconds'), message=ev.get('message'), end=ts)

    def post_event(self, ev):
        ev['ts'] = time.time()
        with self.lock:
            self.apply(ev)
            self.append(ev)
        self.broadcast({'type': 'event', 'event': ev})

    def put_frame(self, agent_id, jpeg):
        now = time.time()
        with self.lock:
            self.frames[agent_id] = (jpeg, now)
            due = now - self.frame_sent.get(agent_id, 0) >= 0.25
            if due:
                self.frame_sent[agent_id] = now
        if due:
            self.broadcast({'type': 'frame', 'agent': agent_id, 'ts': now})

    def put_shot(self, agent_id, run, name, jpeg):
        shot_id = uuid.uuid4().hex[:12]
        (self.shots_dir / f'{shot_id}.jpg').write_bytes(jpeg)
        self.post_event({'kind': 'shot', 'agent': agent_id, 'run': run, 'name': name, 'shot': shot_id})
        return shot_id

    def upsert_agent(self, agent_id, fields):
        fields = {k: v for k, v in fields.items() if k in AGENT_FIELDS and v is not None}
        if 'port' in fields:
            fields['port'] = int(fields['port'])
        with self.lock:
            old = self.agents.get(agent_id, {}).get('status')
            ev = {'kind': 'agent', 'agent': agent_id, 'ts': time.time(), 'fields': fields}
            ev['created'] = ev['ts']
            self.apply(ev)
            self.append(ev)
            new = self.agents[agent_id]['status']
        if 'status' in fields and fields['status'] != old:
            self.post_event({'kind': 'status', 'agent': agent_id, 'text': fields['status']})
        self.broadcast({'type': 'agent', 'agent': agent_id})
        return self.agents[agent_id]

    def archive_except(self, keep):
        with self.lock:
            ids = [i for i, a in self.agents.items() if a.get('status') != 'archived' and i not in keep]
        for i in ids:
            self.upsert_agent(i, {'status': 'archived'})
        return ids

    def resolve(self, body):
        if body.get('agent'):
            return body['agent']
        port = body.get('port')
        if port in (None, ''):
            raise ValueError('agent or port required')
        port = int(port)
        with self.lock:
            cands = [a for a in self.agents.values() if a.get('port') == port]
            if cands:
                return max(cands, key=lambda a: a['updated'])['id']
        agent_id = f'port-{port}'
        self.upsert_agent(agent_id, {'port': port, 'title': f'Port {port}'})
        return agent_id

    # ---- views -------------------------------------------------------
    def agent_view(self, a):
        last_action = next((e for e in reversed(self.events) if e['agent'] == a['id'] and e['kind'] == 'action'), None)
        runs = [r for r in self.runs.values() if r['agent'] == a['id']]
        last_run = max(runs, key=lambda r: r['ts']) if runs else None
        v = dict(a)
        v['lastAction'] = last_action
        v['lastRun'] = last_run
        return v

    def state(self):
        with self.lock:
            return {'agents': sorted((self.agent_view(a) for a in self.agents.values()), key=lambda a: -a['updated']), 'now': time.time()}

    def agent_events(self, agent_id):
        with self.lock:
            return {'events': [e for e in self.events if e['agent'] == agent_id],
                    'runs': sorted((r for r in self.runs.values() if r['agent'] == agent_id), key=lambda r: r['ts'])}

    def run_list(self, suite):
        with self.lock:
            return sorted((r for r in self.runs.values() if not suite or r['suite'] == suite), key=lambda r: -r['ts'])

    # ---- live stream -------------------------------------------------
    def broadcast(self, msg):
        for q in list(self.listeners):
            q.put(msg)


def make_handler(store, page):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype='application/json'):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_GET(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split('/') if p]
            qs = parse_qs(u.query)
            if u.path == '/':
                return self._send(200, page.read_bytes(), 'text/html')
            if u.path == '/api/state':
                return self._send(200, store.state())
            if u.path == '/api/runs':
                return self._send(200, store.run_list((qs.get('suite') or [''])[0]))
            if len(parts) == 4 and parts[:2] == ['api', 'agents'] and parts[3] == 'events':
                return self._send(200, store.agent_events(parts[2]))
            if len(parts) == 4 and parts[:2] == ['api', 'agents'] and parts[3] == 'frame':
                f = store.frames.get(parts[2])
                return self._send(200, f[0], 'image/jpeg') if f else self._send(404, {'error': 'no frame'})
            if len(parts) == 3 and parts[:2] == ['api', 'shots'] and re.fullmatch(r'[0-9a-f]{12}\.jpg', parts[2]):
                f = store.shots_dir / parts[2]
                return self._send(200, f.read_bytes(), 'image/jpeg') if f.exists() else self._send(404, {'error': 'not found'})
            if u.path == '/api/stream':
                return self._stream()
            self._send(404, {'error': 'not found'})

        def _stream(self):
            q = queue.Queue()
            store.listeners.append(q)
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b': hello\n\n')
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(b'data: ' + json.dumps(msg).encode() + b'\n\n')
                    except queue.Empty:
                        self.wfile.write(b': ping\n\n')
                    self.wfile.flush()
            except (OSError, ValueError):
                pass
            finally:
                store.listeners.remove(q)
                self.close_connection = True

        def do_POST(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split('/') if p]
            try:
                n = int(self.headers.get('Content-Length') or 0)
                raw = self.rfile.read(n)
                if u.path in ('/api/frame', '/api/shots'):
                    qs = {k: v[0] for k, v in parse_qs(u.query).items()}
                    agent_id = store.resolve(qs)
                    if u.path == '/api/frame':
                        store.put_frame(agent_id, raw)
                        return self._send(200, {'ok': True})
                    return self._send(200, {'shot': store.put_shot(agent_id, qs.get('run', ''), qs.get('name', ''), raw)})
                body = json.loads(raw or b'{}')
                if u.path == '/api/agents/archive':
                    return self._send(200, {'archived': store.archive_except(body.get('except') or [])})
                if len(parts) == 3 and parts[:2] == ['api', 'agents']:
                    return self._send(200, store.upsert_agent(parts[2], body))
                if u.path == '/api/events':
                    kind = body.get('kind')
                    if not kind:
                        return self._send(400, {'error': 'kind required'})
                    ev = dict(body)
                    ev['agent'] = store.resolve(body)
                    store.post_event(ev)
                    return self._send(200, ev)
            except (ValueError, TypeError) as e:
                return self._send(400, {'error': str(e)})
            self._send(404, {'error': 'not found'})

    return Handler


def serve(args):
    store = Store(args.data)
    page = Path(__file__).with_name('index.html')

    def daily():
        while True:
            time.sleep(24 * 3600)
            store.rewrite()
    threading.Thread(target=daily, daemon=True).start()
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(store, page))
    srv.daemon_threads = True
    print(f'agent-board on http://127.0.0.1:{args.port} (data: {store.dir})', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def post(args, path, body):
    req = urllib.request.Request(args.url.rstrip('/') + path, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except (urllib.error.URLError, OSError) as e:
        if args.verbose:
            print(f'agent-board: {e}', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description='Live board for coding agents and test runs')
    ap.add_argument('--url', default=os.environ.get('AGENT_BOARD_URL', DEFAULT_URL))
    ap.add_argument('-v', '--verbose', action='store_true')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('serve')
    s.add_argument('--port', type=int, default=8120)
    s.add_argument('--data', default='~/.local/share/agent-board')
    a = sub.add_parser('agent')
    a.add_argument('id')
    for f in AGENT_FIELDS:
        a.add_argument('--' + f)
    e = sub.add_parser('event')
    e.add_argument('id')
    e.add_argument('text')
    r = sub.add_parser('archive')
    r.add_argument('--except', dest='keep', nargs='*', default=[])
    args = ap.parse_args()
    if args.cmd == 'serve':
        serve(args)
    elif args.cmd == 'agent':
        post(args, '/api/agents/' + args.id, {f: getattr(args, f) for f in AGENT_FIELDS})
    elif args.cmd == 'event':
        post(args, '/api/events', {'agent': args.id, 'kind': 'action', 'text': args.text})
    elif args.cmd == 'archive':
        post(args, '/api/agents/archive', {'except': args.keep})


if __name__ == '__main__':
    main()
