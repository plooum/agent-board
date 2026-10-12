"""Streams a headless Chrome (Playwright page) to the agent board, read-only. Needs only the Playwright objects passed in.

start(page, board_url, port, project=None): CDP screencast, only the latest frame is posted (a background thread drops older ones).
shot(page, board_url, port, run, name, project=None): posts one JPEG screenshot as a finished test's picture.
Everything is fire and forget: a board that is down never slows or fails the caller.
"""
import base64
import threading
import time
import urllib.request
from urllib.parse import urlencode


def _post(url, data, timeout=0.5):
    try:
        urllib.request.urlopen(urllib.request.Request(url, data, {"Content-Type": "image/jpeg"}), timeout=timeout).read()
        return True
    except Exception:
        return False


_last = [None]  # the latest screencast frame, posted as a finished test's picture (no capture)


class _Poster(threading.Thread):
    def __init__(self, url):
        super().__init__(daemon=True)
        self.url, self.latest, self.cv, self.down_until = url, None, threading.Condition(), 0.0

    def push(self, jpeg):
        with self.cv:
            self.latest = jpeg  # an older unsent frame is dropped
            self.cv.notify()

    def run(self):
        while True:
            with self.cv:
                while self.latest is None:
                    self.cv.wait()
                jpeg, self.latest = self.latest, None
            if time.time() < self.down_until:
                continue
            if not _post(self.url, jpeg):
                self.down_until = time.time() + 5  # board down: stop trying for a few seconds


def start(page, board_url, port, project=None):
    """Starts the screencast of `page` (it survives page loads in the same tab)."""
    try:
        poster = _Poster(f"{board_url.rstrip('/')}/api/frame?{urlencode({k: v for k, v in {'port': port, 'project': project}.items() if v})}")
        poster.start()
        cdp = page.context.new_cdp_session(page)

        def on_frame(ev):
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass
            jpeg = base64.b64decode(ev["data"])
            _last[0] = jpeg
            poster.push(jpeg)

        cdp.on("Page.screencastFrame", on_frame)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": 1024, "maxHeight": 768, "everyNthFrame": 2})
    except Exception:
        pass


def shot(page, board_url, port, run, name, project=None):
    """Posts the latest screencast frame as the test's picture (nothing is captured; no frame yet: nothing posted)."""
    jpeg = _last[0]
    if jpeg is None:
        return
    q = urlencode({k: v for k, v in {"port": port, "run": run, "name": name, "project": project}.items() if v})
    threading.Thread(target=_post, args=(f"{board_url.rstrip('/')}/api/shots?{q}", jpeg, 2), daemon=True).start()
