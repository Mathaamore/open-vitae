# Open Vitæ writing guide

Help people find relevant work and prepare honest applications. Lead with what someone can do next. AI is optional assistance; the person makes decisions and submits applications.

## Voice and vocabulary

Use clear, warm English, sentence case and short sentences. Use **job**, **saved jobs**, **application**, **draft**, **workspace**, and **AI and usage** consistently. Use **CV** for the candidate document. Internal code may still call an application a dossier. Application stages are **Not started → Drafting → Ready to review → Ready to apply → Applied**. A prepared draft is never proof of submission.

Buttons name the next action: **Add a job**, **Save**, **Preview import**, **Get started**. Avoid technical labels such as artifact, inference and backend in ordinary screens. Explain formats where they matter: a JSON file is needed when exchanging an AI response. Remove badges that repeat nearby text.

Empty states explain what belongs there and give one useful next action. Errors say what failed and how to recover; never blame the person or promise success. Keep uncertainty visible: **Team not confirmed** is better than an invented employer fact. Do not invent experience, enthusiasm, eligibility, company claims or demographic answers.

Explain privacy at the action: local work stays in the workspace; sharing a prompt is the user's choice; connecting AI sends bounded context to the selected provider. Provider charges and policies are separate. Request counts are not a balance. Consent remains explicit and submission remains manual.

## Copy inventory and ownership

| Surface | Source | Purpose |
| --- | --- | --- |
| Welcome, profile, search, saved jobs, application review, AI settings/import/export | `src/job_agent/web/copy.en.js`, HTML and rendering functions | Explain actions and states without changing user text |
| Validation, preparation, providers, downloads and recovery | `src/job_agent/locales/en.json` | Actionable messages and complete parameterized sentences |
| Mac menus, dialogs and startup | `macos/en.lproj/Localizable.strings` and Swift `L()` | Standard Mac terminology and recovery |
| Landing page, privacy, terms, unavailable release and 404 | `site/copy.en.js` and readable HTML fallback | Product value, honest availability and clear next steps |
| Portable examples and prompts | `portable.py`, catalogs and `docs/portable/` | Ground responses in supplied facts and require review |

English is the default and fallback. Browser copy uses `t(key, values)` and `data-i18n`; Python uses `tr(key, **values)`. Keep full sentences together and substitute named values. Escape rendered values; never put user content into translation keys. Additional browser catalogs can register with `I18n`; re-render dynamic views when changing locale. Native strings use the platform localization API with English keys as fallback. No language picker is shipped.

Never translate saved profiles, CVs, job descriptions, employer questions or application prose. `system_text()` handles known historical app notices only at display boundaries, leaving stored data intact. Update English HTML fallbacks alongside catalogs. Tests cover fallback, interpolation, historical notices and preservation of source text.

## Hero decision

- **Find work worth pursuing.** Selected: specific to discovery and personal fit, with room for the supporting sentence to explain preparation and control.
- **A clearer path to your next role.** Too generic; it could describe a course or recruiter.
- **Your next move, thoughtfully prepared.** Warm, but hides discovery and overemphasizes documents.

The supporting copy explains finding suitable jobs, understanding a role and preparing from actual experience. The availability action stays honest until a verified Mac installer exists. No claims of guaranteed interviews, automated applications or fabricated social proof.

## Interaction hierarchy

Discovery keeps its message composer visible. Conversation history and job results scroll inside their respective panes; the surrounding window stays fixed. Small windows show Conversation and Suggested jobs as separate panels rather than stacking both. Search works without AI. A disconnected chat offers **Connect AI** and preserves typed text. The sidebar separates discovery, application tracking and external AI imports, with account status beside AI settings. Connecting a service stays in a dialog over the workspace rather than restarting onboarding.

The UI UX Pro Max review prioritizes visible form labels, bounded viewport layout, honest connection state, progress and recovery, keyboard focus and contrast. Existing Geist typography and green brand tokens remain; this is a workflow correction rather than a new visual identity. Browser checks exercise long transcripts, small laptop windows, mobile widths, modal dismissal, failed sign-in and retry, and restored connection state using fictional providers.

## Workspace layout

The Mac app uses a fixed frame with a quiet sidebar and a stable screen header. Tracker, application, AI imports and settings each use one main page scroller. Discovery deliberately has two content scrollers on a wide window, with bounded history and results; compact windows switch between those panes. Do not add another viewport height or nested scrolling wrapper to a screen. Use the existing content container.

Long PDF previews are optional and collapsed until requested. Adding a job starts with its link and exposes manual details on request or retrieval failure. Settings group AI connection, job sources and workspace exports. Notifications can be dismissed and do not push the message field around. The browser regression checks use long conversations and result lists at 840 × 580 through 1440 × 900, with small mobile widths, light/dark appearance and reduced motion.

## Preparing a saved job

**Prepare with ChatGPT** (or the connected service) runs integrated preparation directly from either a suggestion or a saved job. Show the queue/progress inside the job, open the materials when ready, and then offer **Review materials**. **Other ways to prepare** contains the external prompt and manual editor; never send someone there as the default AI action. A failed provider request stays visibly failed, with an explicit retry. A new AI version keeps prior drafts and files in history and cannot overwrite a concurrent edit. No preparation chooses consent, confirms eligibility or submits an application.
