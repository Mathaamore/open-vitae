"""Render the shared README/social cover using local assets only."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(
        ('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{server.server_port}/design/brand/open-vitae/visuals/cover.html')
            page.evaluate('document.fonts.ready')
            assert page.locator('img').evaluate_all(
                '(images)=>images.every(image=>image.complete&&image.naturalWidth>0)')
            page.screenshot(path=str(ROOT / 'site/assets/open-vitae-cover.png'))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
