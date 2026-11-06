# Open Vitæ

![Open Vitæ — Find work worth pursuing. Open source, made for Mac, AI optional.](site/assets/open-vitae-cover.png)

**A local, open-source Mac workspace for a thoughtful job search.** Discover relevant roles, prepare applications from your real experience and follow each conversation through to its outcome.

[Website](https://open-vitae.mathaamore.xyz/) · [Getting started](#run-from-source) · [Architecture](docs/ARCHITECTURE.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)

**Early preview · macOS 14+ · Apple Silicon · English interface**

## From first look to next step

- **Discover.** Import an offer from a URL, a description or manual fields. Explore public feeds and configured employer boards, with local ranking and reasons for each match.
- **Prepare.** Import your CV, keep your experience as the source of truth and build editable CVs and application answers. Export documents, save versions and review everything before sending.
- **Track.** Record applications, replies, interviews, offers, rejections and withdrawals. Keep dated notes and activity history alongside each opportunity.

Your profile, CV imports, saved jobs, drafts and tracker work offline without an account or AI key. Online discovery and AI assistance are optional. You submit applications yourself on the employer’s site.

<details>
<summary>See the application workspace</summary>

![The application with a fictional candidate and jobs](docs/images/workspace.png)

Screenshots and tests use fictional profiles and opportunities.

</details>

## The stack

Open Vitæ is a native Mac shell around a local web application. The interface talks to a Python service bound to loopback; your workspace stays on your computer.

| Layer | Technology | Responsibility |
|---|---|---|
| Mac application | Swift, AppKit, WKWebView | Native window and lifecycle; starts the bundled local service |
| Local service | Python 3.11+, FastAPI, Uvicorn | Workspace operations, job discovery, preparation and provider integration |
| Interface | HTML, CSS, vanilla JavaScript, Geist | Onboarding, job review, document editing and application tracking |
| Storage | SQLite and local files | Profiles, jobs, activity history, document versions and backups |
| Documents | ReportLab, pypdf, pdfplumber, standard-library DOCX/TXT parsing | One-page PDF export, imported PDF layouts and text imports; scanned PDFs require OCR elsewhere |
| Browser automation | Playwright and Chromium | Read public employer pages and inspect forms; never submit applications |
| Optional AI | Official Codex app-server, Anthropic API, Google Gemini API | Assistance using the candidate’s chosen provider |
| Packaging | PyInstaller, native Swift shell; Sparkle for release updates | Bundle the Python runtime and desktop dependencies |
| Marketing website | Static HTML, CSS and JavaScript on Vercel | Public information and verified release availability |
| Checks | Python unittest, Node test runner, Playwright | Service tests, interface logic and browser journeys |

There is no React build pipeline or Node runtime requirement for the application or website. Node is used for JavaScript tests. See the [architecture and code map](docs/ARCHITECTURE.md) for module boundaries and data flow.

## Languages and CV layout

Explanations, company briefs and AI revision notes follow the app language (currently English). CVs and application answers follow the employer’s form language, detected from its questions, page language or listing. English is the fallback when detection is inconclusive. Override ambiguous detection with **Edit job → Application language**. English, French, German, Spanish, Italian, Dutch and Portuguese are supported. Imported source material stays unchanged; prepare a new version to update older drafts.

Import a **one-page text PDF** to reuse its page layout, graphics, text positions, sizes and colors. The original is stored privately and never overwritten. Adaptation translates or rephrases each text zone without adding experiences. Standard PDF fonts and embedded TrueType fonts are reused when available; unsupported fonts or missing glyphs use Geist. Complex/rotated layouts can require a simpler source PDF. Review every exported version, especially tightly spaced or mixed-style lines.

DOCX, TXT and multi-page PDFs remain text imports; they do not preserve their original layout. Export them to a one-page PDF first to use them as a layout template. Without a PDF template, the app uses its simple CV layout. **Every successful generated CV has exactly one page.** Exports that would overflow or need illegible text fail with an explanation, rather than silently dropping content. Shorten the source or use a roomier template and try again. Offline/manual drafts cannot translate by themselves; integrated or portable AI preparation can translate the CV, with human review.

## AI on your terms

Local discovery and ranking use no model tokens. Prepare drafts yourself, use an integrated provider or take a portable prompt to another AI and review its result before importing it.

| Provider | Connection | Account and billing |
|---|---|---|
| ChatGPT | Official local Codex app-server browser sign-in | Your account’s access and usage limits apply |
| Claude | Anthropic API key in the OS keyring | Separate API billing; does not connect a Claude subscription |
| Gemini | Google AI Studio API key in the OS keyring | Project quota or billing; does not connect a Gemini subscription |

Requests use bounded context and are serialized. The default limit is 20 model requests per UTC day, adjustable from 1 to 100; failures count conservatively. There are no automatic retries or model upgrades. API responses have output-token limits; Codex does not expose a strict per-turn output cap. Only provider-reported usage is displayed.

Read about [providers and limits](docs/PROVIDERS.md) or the [portable AI and offline workflow](docs/PORTABLE_AI.md). Public distribution requirements for the ChatGPT integration still need verification before shipping binaries.

## Run from source

Requires **Python 3.11+**. These commands create a separate temporary development workspace; it may be removed by the operating system. Choose a persistent directory for your own work.

```sh
git clone https://github.com/Mathaamore/open-vitae.git
cd open-vitae
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m playwright install chromium --only-shell
.venv/bin/python -m job_agent.main --workspace /tmp/open-vitae-dev
```

Open **http://127.0.0.1:8765**, choose **Get started** and add a profile and an offer. Connect an AI provider later if you want assistance. Source-based ChatGPT integration requires the official Codex CLI on `PATH`; API providers require a working OS keyring. Tests use fake providers and need no keys.

Without `--workspace`, the default Mac directory is `~/Library/Application Support/Candidatures` (the historical name is retained for compatibility). Linux uses `$XDG_DATA_HOME/candidatures` or `~/.local/share/candidatures`.

### Mac app availability

The desktop shell targets **macOS 14+ on Apple Silicon** and bundles the Python service, Codex and Chromium. End users of the bundled app do not need a terminal.

**No verified, notarized public installer is available yet.** Local builds are ad-hoc signed. Developer ID signing, notarization, DMG packaging and Sparkle update tooling exist, but public release and clean-Mac verification remain outstanding. See [Mac build instructions](macos/README.md) and the [release runbook](docs/RELEASING.md).

### Website

The landing lives in [`site/`](site/README.md) and never connects to the local application. Vercel settings: **Root Directory `site`**, framework **Other**, no build command, output **`.`**. The download stays unavailable until a maintainer records a verified release. [Visual sources and generation prompt](design/brand/open-vitae/visuals/README.md).

## Your workspace, your decisions

Profiles, SQLite records and generated documents stay in your chosen workspace. Provider credentials use the OS keyring or an isolated Codex session. Disconnecting a provider keeps your dossiers. There is no built-in telemetry.

AI requests send relevant context to the provider you select. Public feeds receive search terms and optional country filtering, not your CV. Employer metadata retrieval is optional; integrated preparation may anonymously read public employer pages. Portable prompts can contain CV details: review them before sharing.

Job coverage is partial and openings can be stale. Matches do not establish eligibility. You verify facts, review answers, choose consent and demographic responses, and send the application yourself. Dynamic forms may need manual completion. The local service must stay private; see [SECURITY.md](SECURITY.md).

## Contribute

Start with [CONTRIBUTING.md](CONTRIBUTING.md), the [architecture](docs/ARCHITECTURE.md) and the [roadmap](docs/ROADMAP.md). Bug reports, accessibility improvements and focused fixes are welcome. Use fictional data in tests, screenshots and issues.

```sh
.venv/bin/python -m unittest discover -s tests -q
node --test tests/test_web.js
.venv/bin/python scripts/check_product_ui.py
.venv/bin/python scripts/check_offline_ui.py
.venv/bin/python scripts/check_landing_ui.py
# After staging, inspect what Git would publish:
.venv/bin/python scripts/check_repository.py
```

Browser tests exercise fictional providers and jobs; they do not prove access to every real account or employer website. Job source coverage and limits are documented in [SOURCES.md](docs/SOURCES.md).

## License

Original code and project brand assets are [MIT licensed](LICENSE). Fonts, bundled tools and job content retain their own licenses and terms; see [third-party notices](THIRD_PARTY_NOTICES.md). Open Vitæ is an independent project.
