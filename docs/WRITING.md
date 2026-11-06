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
