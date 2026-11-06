# Public website

Static HTML, CSS, a small progressive-enhancement script and bundled brand assets. It is independent of the Python service: no API routes, provider calls, candidate storage, account system, cookies or analytics. The screenshot shows the real app with fictional data.

## Vercel

Import this Git repository. Set **Root Directory = `site`**, **Framework Preset = Other**, no install/build command, **Output Directory = `.`**. `vercel.json` provides security headers and clean URLs. Do not deploy the repository root or expose the local service. No environment secrets are required. Deploying is a maintainer action; this checkout has not been published.

For a local preview, serve this directory with any static HTTP server. Run `python scripts/check_landing_ui.py` from the repository's test environment for browser QA. It checks 390/768/1024px widths, assets, dark/reduced-motion states and the release link boundary without contacting GitHub.

`release.json` defaults to unavailable. After the [release acceptance](../docs/RELEASING.md) succeeds, set `verified: true`, `version: "<semver>"`, and the exact `https://github.com/Mathaamore/open-vitae/releases/download/v<semver>/Open-vitae-Mac.dmg` URL. The script accepts only that repository and artifact shape. Keep the FAQ's availability text in sync. Verification is a maintainer attestation, not something the browser can establish. If JavaScript or the JSON fetch fails, the page keeps its honest development message and links to GitHub Releases.

English is the default and fallback language. `copy.en.js` owns website copy; `data-i18n` attributes and `i18n.js` apply it without interpreting HTML. Keep the readable HTML fallback in sync. See [the writing guide](../docs/WRITING.md). Add translated pages and hreflang links only when translations and a production domain exist. The production canonical URL is `https://open-vitae.mathaamore.xyz/`. Open Graph and Twitter cards use the absolute URL of `assets/open-vitae-cover.png` (1200 × 630). Keep these URLs in sync if the domain changes.

Bundled Geist is SIL OFL; see `assets/Geist-OFL.txt`. Original Open Vitæ brand assets and code are MIT licensed. No fabricated testimonials or provider integration badges are used.

The landing illustration and shared README/social cover have [editable sources, rendering instructions and the final ImageGen prompt](../design/brand/open-vitae/visuals/README.md). The cover uses the existing logo and font; the application screenshot remains a real capture with fictional data.
