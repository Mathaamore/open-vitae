# Project visuals

The landing uses `site/assets/application-folio.webp`: an illustration generated with the built-in OpenAI ImageGen tool, then encoded to WebP at its original 1536 × 1024 size. No CLI image-generation fallback was used.

The README and social cards share `site/assets/open-vitae-cover.png` (1200 × 630). `cover.html` composes the existing SVG logo, bundled Geist font, exact project copy and the illustration. This keeps text and branding deterministic.

To render the cover, run from the repository root with the test dependencies and Playwright Chromium installed:

```sh
.venv/bin/python design/brand/open-vitae/visuals/render.py
```

The renderer uses a temporary loopback HTTP server, waits for fonts and verifies that every image loaded. It writes only the cover asset. The landing QA checks the exported dimensions and social metadata.

## Final ImageGen prompt

Transparent background was enabled.

> Use case: ads-marketing. Asset type: premium editorial product illustration for Open Vitæ, an open-source macOS workspace for a thoughtful job search. Create a beautifully art-directed tactile paper sculpture on a genuinely transparent background: a single open deep forest-green document folio, with three substantial ivory paper sheets emerging from it and gently folding into an ascending architectural passage. One thin pear-green divider sheet gives a fresh accent. The gesture should suggest personal experience becoming an application and a next step, not a generic growth chart. Three-quarter studio view, sculptural precise folded edges, restrained dimensionality, soft realistic contact shadows contained near the object. Materials: very fine uncoated paper, matte forest-green cover, no glossy plastic. Brand colors: forest #214B40, pear #D8EDA2, ivory #F5F6F2. Compose a compact coherent object with generous clear transparent space around it, no cropping, landscape format. It should feel like an independent Mac utility's premium launch artwork, mature, calm and human. Absolutely no text, letters, logos, UI, charts, graphs, arrows, icons, checkmarks, people, laptop, plants, floating random objects, watermark or background scenery. Keep the shapes few, intentional, elegant, plausible and clean.
