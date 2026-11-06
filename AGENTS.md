# Working on Open Vitæ

- Read README.md and CONTRIBUTING.md before changing a workflow.
- Use temporary workspaces and fictional profiles. Never use a contributor's real provider account, CV or applications for a test.
- Keep local-only HTTP protections, keyring storage, bounded provider context, explicit consent and manual submission intact.
- Candidate facts are source material. Do not invent experience, enthusiasm, employer claims or demographic answers.
- Run the relevant tests and `python scripts/check_repository.py` after staging. Review the staged diff; never add runtime data or credentials.
- Keep fixes small and finish their callers, docs and tests. Avoid adding infrastructure that the current app does not need.
