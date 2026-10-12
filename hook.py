#!/usr/bin/env python3
"""Claude Code PostToolUse hook: posts an agent's commands and file edits to the agent board.

Reads the hook JSON on stdin. Never slows, breaks or talks into a session:
short timeout, every error swallowed, always exit 0, prints nothing.

  hook.py [--url URL] [--only-under SUBSTRING]
"""
import argparse
import json
import os
import sys
import urllib.request


def checkout_root(path):
    p = os.path.abspath(path)
    if not os.path.isdir(p):
        p = os.path.dirname(p)
    while True:
        if os.path.exists(os.path.join(p, '.git')):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default=os.environ.get('AGENT_BOARD_URL', 'http://127.0.0.1:8120'))
    ap.add_argument('--only-under', default=None)
    args, _ = ap.parse_known_args()
    data = json.load(sys.stdin)
    tool, inp = data.get('tool_name'), data.get('tool_input') or {}
    cwd = data.get('cwd') or os.getcwd()
    path = inp.get('file_path') or inp.get('notebook_path')
    if tool == 'Bash':
        cmd = inp.get('command') or ''
        text = (inp.get('description') or (cmd.splitlines() or [''])[0])[:120]
        root = checkout_root(cwd)
    elif tool in ('Edit', 'Write', 'NotebookEdit') and path:
        full = path if os.path.isabs(path) else os.path.join(cwd, path)
        root = checkout_root(full)
        if not root:
            return
        text = ('Write ' if tool == 'Write' else 'Edit ') + os.path.relpath(full, root)
    else:
        return
    if not root or not text.strip():
        return
    if args.only_under and args.only_under not in root + '/':
        return
    body = json.dumps({'agent': os.path.basename(root), 'kind': 'action', 'text': text}).encode()
    req = urllib.request.Request(args.url.rstrip('/') + '/api/events', body,
                                 {'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=0.5).read()


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
