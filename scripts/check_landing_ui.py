"""Static landing QA, including the verified-release trust boundary; no external calls."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT/'site')))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output=ROOT/'data/qa';output.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            url=f'http://127.0.0.1:{server.server_port}'
            page.goto(url);expect(page.locator('h1')).to_contain_text('Find work')
            expect(page.locator('#release-status')).to_contain_text('No verified public installer')
            assert page.locator('.product>img').evaluate('(image)=>image.complete && image.naturalWidth>0')
            assert page.locator('.hero-art img').evaluate('(image)=>image.complete && image.naturalWidth>0')
            production = 'https://open-vitae.mathaamore.xyz/'
            expect(page.locator('link[rel="canonical"]')).to_have_attribute('href', production)
            expect(page.locator('meta[property="og:url"]')).to_have_attribute('content', production)
            for selector in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
                expect(page.locator(selector)).to_have_attribute('content', production + 'assets/open-vitae-cover.png')
            expect(page.locator('meta[property="og:image:width"]')).to_have_attribute('content', '1200')
            expect(page.locator('meta[property="og:image:height"]')).to_have_attribute('content', '630')
            page.evaluate("""async () => {
                const image = new Image(); image.src = 'assets/open-vitae-cover.png';
                await image.decode();
                if (image.naturalWidth !== 1200 || image.naturalHeight !== 630) throw Error('Invalid social cover dimensions');
            }""")
            page.screenshot(path=str(output/'landing-hero.png'))
            page.screenshot(path=str(output/'landing-desktop.png'),full_page=True)
            for width in (390,768,1024):
                page.set_viewport_size({'width':width,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
                assert page.locator('[data-download]').bounding_box()['y'] < 844
            page.set_viewport_size({'width':390,'height':844});page.emulate_media(reduced_motion='reduce')
            page.screenshot(path=str(output/'landing-mobile.png'),full_page=True)
            page.emulate_media(color_scheme='dark')
            page.screenshot(path=str(output/'landing-dark.png'),full_page=True)
            for bad in ['javascript:alert(1)','https://github.com.evil.example/installer.dmg','https://github.com/Other/repo/releases/download/v1.2.3/Open-vitae-Mac.dmg']:
                page.route('**/release.json',lambda route,request,bad=bad:route.fulfill(json={'verified':True,'version':'1.2.3','url':bad}))
                page.reload();expect(page.locator('#release-link')).to_have_attribute('href','https://github.com/Mathaamore/open-vitae/releases')
                page.unroute('**/release.json')
            release={'verified':True,'version':'1.2.3','url':'https://github.com/Mathaamore/open-vitae/releases/download/v1.2.3/Open-vitae-Mac.dmg'}
            page.route('**/release.json',lambda route:route.fulfill(json=release))
            page.reload();expect(page.locator('[data-download]')).to_have_attribute('href',release['url'])
            page.goto(url+'/404.html');expect(page.locator('h1')).to_contain_text('This page isn’t here.')
            assert not errors,errors
            browser.close()
        print('Landing passed: responsive, light/dark, reduced motion, real assets, honest availability, verified release URL checks, custom 404.')
    finally:
        server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    main()
