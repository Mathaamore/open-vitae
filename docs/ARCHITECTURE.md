# Architecture

A native Mac window wraps a loopback-only FastAPI service. SQLite and documents live in the user's chosen workspace, outside the app bundle. The web interface uses local JavaScript/CSS and bundled fonts.

| Location | Responsibility |
|---|---|
| `src/job_agent/app.py` | Local session/origin checks, optional provider operations and HTTP endpoints |
| `store.py`, `workspace.py` | Versioned dossiers, candidate profile, explicit feedback, queue state and usage budget |
| `providers.py`, `assistant.py` | Keyring-backed API transports and isolated Codex app-server integration |
| `sources.py`, `ats.py`, `net.py` | Public feeds, local ranking and bounded HTTPS requests with public-address checks |
| `packets.py`, `browser.py` | Read-only form inventory, factual preparation and PDF generation |
| `delivery.py` | Downloadable draft email assembly; no sending transport |
| `opportunities.py`, `portable.py` | Canonical manual jobs, explicit public metadata retrieval, local drafts, portable artifact validation/prompting and private backups |
| `web/` | Onboarding, conversation, suggestions, dossiers and tracking UI |
| `migrations.py` | Integrity checks, private backups before schema changes and newer-schema protection |
| `site/` | Independent static French website, Vercel configuration and curated verified-release link |
| `macos/` | Native shell, packaged service launcher and local build script |
| `tests/`, `scripts/check_product_ui.py` | Fictional fixtures, unit checks and isolated browser journey |
| `design/brand/open-vitae/` | Logo masters, font notice and brand guide |

Accepting an offer queues preparation. One model request produces a bounded structured result, validated before artifacts are written. Existing or submitted dossiers are protected. The user reviews, checks eligibility/form details, completes the employer's submission and records the send manually.

For compatibility, workspaces can contain a private `data/company-context.json` with company/role notes. It is never part of a source checkout or packaged build. Candidate imports and legacy workspace selection are local operations; they do not synchronize or publish data.
