# Offline workspace and portable AI

Open Vitæ opens your local workspace without checking a provider or requiring an account. Choose **Get started** during onboarding. Saved jobs, profile/CV import and editing, favorites, dossier editing, local PDF generation, prompts and exports need no internet. Discovery, optional employer-page retrieval and integrated inference need network access. Failures leave local data accessible. Choosing local mode does not delete a previously connected account; disconnect explicitly in settings when needed.

## Any opportunity, one tracker

**Add a job** accepts a public HTTPS URL, pasted description or manual fields. Missing company/title fields are visibly marked as incomplete, never inferred. An URL-only job is saved as pending retrieval. **Edit job** lets you retrieve later or paste missing information without creating another job. Retrieval is an explicit GET through the bounded, DNS-pinned public network client. It reads `JobPosting` JSON-LD only; scripts are never executed. Unsupported, blocked or offline pages immediately offer pasted text/manual entry. Published salary is extracted only when its structured currency, amount and period are available; other missing facts stay blank.

Manual and external-AI jobs appear in the same tracker as feed jobs. **Save** places a suggestion in **Saved jobs**. Local CV and draft controls are available from **Prepare without AI** on any job. A newly generated local draft creates another dossier version; it does not submit, approve, select consent or answer demographics. Imported AI prose remains an editable draft. Editing an opportunity clears obsolete ranking/analysis/verification and revokes previous dossier approval, preserving the dossier and its versions. Submitted/uncertain submissions cannot be changed through imports or edits.

URL identity lowercases the host, removes the HTTPS default port, trailing slash, ordinary page-anchor fragments and known marketing parameters (`utm_*`, `gclid`, `fbclid`), and sorts remaining query parameters. Job identifier parameters such as `gh_jid` and routing fragments beginning with `/` or `!` are preserved. Other job IDs encoded in fragments may need source-specific handling. Existing jobs are matched using this identity across manual, AI and feed sources; their contents are not silently replaced. Different URLs that represent the same underlying role may still need human reconciliation. Text-only jobs have distinct local IDs and no fake employer URL.

## Copy → generate externally → preview → import

1. Open **Use my AI** and choose profile analysis, job search, job analysis or application preparation. Job-specific tasks require a selected saved job.
2. Generate the prompt locally. It contains the exact envelope/context to preserve, bounded profile/job material and numbered source facts. Name/contact fields are omitted, but CV lines can still contain personal information. Read and edit the prompt before sharing. Nothing is sent to an external model by this action.
3. Copy it to your chosen service yourself. Its privacy, billing and browsing capabilities apply. A model without browsing should not invent job search results. Ask it for a JSON file matching the provided format, without Markdown fences.
4. Drop/select the returned JSON, or paste it. **Preview import** validates and shows the content and duplicates without writing data. Changing the input disables confirmation until another preview.
5. Confirm that exact preview. The server revalidates against current profile/job context; stale files require a new prompt. Duplicate listings reuse their existing records. Profile analyses are stored as suggestions separate from candidate facts. Job analyses are labelled external and unverified. Application drafts create an editable version and select only existing numbered facts for the PDF.

Connect an integrated AI later from **AI and usage**. Disconnected chat offers the portable workflow; it does not force a setup screen. If integrated preparation fails, the app shows the error and preserves existing materials; it never reports a local fallback as successful AI preparation. Choose the separate manual workflow when wanted. Reconnecting does not create a separate workspace or tracker.

## Version 1 envelope

See the downloadable [JSON Schema](portable/schema-v1.json) and examples:

- [`profile_analysis`](portable/profile_analysis.example.json): `summary`, `strengths`, `uncertainties`. These do not modify profile experience or criteria.
- [`job_search_results`](portable/job_search_results.example.json): 1–30 `jobs`, each with company, role and public HTTPS source URL; optional description/location/salary. No live/verified/submitted status is accepted.
- [`job_analysis`](portable/job_analysis.example.json): summary, strengths, uncertainties and public source URLs. No inferred company facts or eligibility flags are promoted to verified state.
- [`application_draft`](portable/application_draft.example.json): summary, motivation and up to five `selected_facts` indices into the prompt's numbered facts. No external file paths, consent answers, form definitions or submission commands are accepted.

Every file has exactly `schema_version: 1`, `type`, `context` and `data`. Context contains the current integer `profile_revision`; job artifacts additionally bind `job_id`, `job_revision` and `job_updated_at`. Static documentation examples contain fictional context; use **Download example JSON** in the app for a file with your actual current context. Future schema versions are rejected with a clear instruction; no speculative migrations are introduced for v1.

Files are UTF-8 JSON, at most 1 MB. Unknown fields, duplicated JSON keys, non-finite numbers, unsafe URLs, invalid lists/indices and stale context are rejected. All rows are validated before job insertion; if storage fails during a batch, retrying reuses any already saved URLs. Untrusted strings render as text, not HTML or commands. Structural validation cannot prove that an AI's prose is true; reviewing it remains necessary. Nothing imports an application submission or chooses consent.

The schema is generated by `portable.schema()` and kept under `docs/portable`; runtime validation uses the same versioned contracts without introducing another dependency. Prompts are limited to 48,000 characters, 120 numbered facts and 12,000 characters of factual extracts; company/job context is bounded too. No provider key, session directory or browser credential is included.

## Export, backup and recovery

**Export profile and tracker** produces a private JSON export for inspection/portability. It is not an AI response artifact and cannot be imported through the AI importer. **Back up workspace** creates a ZIP containing a consistent SQLite snapshot plus dossier/version files. Provider credentials, Codex sessions, browser profiles, migration backups and service logs are excluded. Treat both downloads as personal documents.

To recover, quit Open Vitæ. Keep a copy of the failed workspace. Extract the trusted backup into a new private folder, with `data/agent.sqlite3` directly inside that folder. Use **File → Open Workspace…** to open it. Never replace a running database or discard the only copy. Reconnect providers separately; credentials are not part of a portable backup. The backup ZIP was tested by restoring to a separate temporary workspace; it has no automatic restore endpoint accepting arbitrary archives.

Tests use fictional candidate files, fake providers and blocked external reads. Run `python -m unittest discover -s tests -q`, `node --test tests/test_web.js`, `python scripts/check_product_ui.py` and `python scripts/check_offline_ui.py`. No real AI account is needed. The portable workflow is JSON-based; a specific external model's ability to follow it is not guaranteed by fixture tests.
