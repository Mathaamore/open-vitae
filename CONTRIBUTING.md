# Contributing to Open Vitæ

Build a useful, free desktop application that helps people express their own experience honestly. The interface must be usable without opening a terminal or editing configuration.

## Before a change

Describe the concrete user problem, expected behavior and smallest useful change. For a substantial workflow or provider addition, open an issue first. Small fixes can go directly to a pull request.

## Local development

Use Python 3.11+, install the project in an isolated environment, and run the local service. Swift command-line tools are required only to build the Mac shell.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m job_agent.main --workspace /tmp/open-vitae-dev
```

## Checks

- Add one focused regression check for logic changes. Use temporary workspaces, fictional profiles and mocked providers; never spend a contributor's tokens by default.
- Verify keyboard navigation, visible focus, reduced motion and small windows for UI changes. Attach screenshots showing the changed workflow.
- Run `python -m unittest discover -s tests -q`, `node --test tests/test_web.js` and the isolated product UI check where applicable.
- Keep new provider behavior explicit: authentication mode, transmitted data, model policy, limits and failure handling. No copied OAuth tokens, plaintext credential fallback, hidden model upgrades or fabricated account balances.
- Keep candidate facts intact. AI suggestions require review. Never infer demographic answers or check consent automatically. Sending is manual.

## Pull requests

Explain the user-facing outcome and how it was checked. Do not commit CVs, profiles, receipts, job databases, sessions, keys, exports or screenshots containing real candidate information. A self-contained small PR is easier to review than unrelated cleanup.

Report sensitive issues privately to the repository maintainer through the hosting platform's private reporting feature when available. Do not include credentials or personal documents in a public issue.
