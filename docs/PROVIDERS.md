# Providers

AI is optional. Connect one provider when you want integrated chat or writing assistance. Authentication and inference are distinct: a successful login/key check does not guarantee model entitlement or remaining quota.

## ChatGPT

Uses the official Codex app-server protocol and browser sign-in. The Mac build bundles the CLI; source development needs `codex` on PATH. CODEX_HOME is isolated under the selected workspace's `data/assistant-session`. Credentials are delegated to the OS keyring; tokens from other applications are never imported or exposed to frontend JavaScript.

Inference uses an ephemeral read-only session with tools and approval requests disabled. A small catalog model is preferred when present; otherwise the account default is used with low reasoning when supported. Context is bounded and turns time out, but app-server does not provide this integration with a strict output-token cap.

Before public binary distribution, review [Sign in with ChatGPT](https://developers.openai.com/siwc) and [Codex app-server](https://learn.chatgpt.com/docs/app-server) requirements and register the application's client where required.

The connection panel stays over the workspace. Choose ChatGPT, request a sign-in link, open it in the system browser, and finish the official flow. The app checks for completion and offers a fresh attempt on failure or timeout. Returning to the app does not submit a model request. On reopening, the app checks the saved connection unless local mode was explicitly selected. A connection indicator confirms authentication, not remaining quota or successful inference.

## Claude and Gemini

These are API integrations, clearly labeled as API keys. They do not authenticate a consumer subscription. Keys are validated with the vendor and stored in the OS keyring. There is no plaintext fallback.

The transports use compact Haiku and Flash-Lite model IDs declared in `providers.py`, bounded context and explicit output-token limits. Models, availability, pricing and provider terms can change. A provider error leaves the original dossier intact; the user can fix access and retry deliberately.

## Request and data policy

At most one inference runs at a time. The default daily request budget is 20, counted in UTC and adjustable from 1 to 100. Failed calls count; exact cached requests avoid another inference. No automatic retry or model upgrade is performed.

Only task-relevant profile facts, selected text, short chat history or public job text are sent. Private search constraints must stay out of employer-facing answers. Suggestions never establish consent or change candidate facts. Search queries exclude contact details. Usage is displayed only when the provider reports it; no subscription credit balance is claimed.

Use fictional profiles and mocked providers in tests. Real account authentication and inference must be checked by the account owner before a release is described as verified for that provider.

## Distribution review (6 November 2026)

[Official app-server guidance](https://learn.chatgpt.com/docs/app-server) permits continued app-server authentication for local/open-source applications and recommends migration to registered Sign in with ChatGPT. It excludes commercial/hosted services. Open Vitæ retains its isolated managed local flow; it does not extract another app’s credentials. A future registered integration must use its own client registration and token lifecycle, following the [official app-server configuration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server). Model listing alone is not proof of inference access. Public release acceptance must verify sign-in and a real inference request using dedicated test access. No provider account was used for this change.
