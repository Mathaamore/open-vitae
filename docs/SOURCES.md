# Discovery sources

Arbeitnow (Europe and UK) and Himalayas remain enabled. Settings can add at most six employer boards as `greenhouse:slug`, `lever:slug`, `lever-eu:slug` or `ashby:slug`. Use the board slug from the employer's official careers link, never a candidate name or email. No curated list of employers or guessed companies is silently added. Board names are displayed as their configured identifiers; this is not a claim about an employer's legal name.

Adapters issue bounded HTTPS GET requests through the existing public-address/DNS-pinned client. No private network, credentials, application POSTs, scraping, CAPTCHA solving or restricted platform integration is introduced. The ATS endpoints are employer-specific public boards; publication does not grant permission to reuse every employer's content. Review the employer's and provider's applicable terms before configuring it.

Each source read is capped at 100 records and 3 MB. The client has a 15-second socket timeout; cancellation is cooperative between reads and rows, so an in-flight read completes first. The UI shows actual completed source reads and collected offers and refreshes recommendations while collection proceeds. The aggregate refresh caches a successful identical search/profile/source configuration for 24 hours; partial failures and cancelled searches can retry immediately. Already collected offers survive cancellation and restart. Discovery progress itself is in memory; on restart a new search can run against saved listings. A separate chat-triggered search still uses the existing synchronous bounded refresh and does not show this cancellable progress UI.

No CV is sent to these feeds. Himalayas receives professional search terms and an optional country. Configured employer boards receive only a board GET. Only HTTPS application links are imported. Listing identity is based on its original URL; this does not deduplicate different ATS and aggregator URLs pointing at the same role. Saved dossiers are not overwritten by a refresh. Absence from a bounded board response does not mark a role closed.

Greenhouse's list `updated_at` is not represented as publication time. Lever's public list has no guaranteed original publication date. Ashby's `publishedAt` is parsed only when timezone-qualified, and unlisted entries are ignored. Unknown dates stay unknown. Existing 45-day feed-age filtering and Himalayas expiry checks remain. Feed presence is not proof the employer is still accepting applications or that the candidate is eligible. The current local matcher explains role/skill overlap and flags unknown work arrangements and salary; an explicit profile checkbox can exclude known remote-work and annual EUR salary conflicts. Unknown conditions remain visible for review. Free-form motivations and geography are not automatically converted into enforceable constraints.

## Official API contracts

- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board): public board GET, no submission endpoint used.
- [Lever Postings API](https://github.com/lever/postings-api): global and EU list GET endpoints.
- [Ashby public postings](https://developers.ashbyhq.com/docs/public-job-posting-api): listed jobs, original job links and explicit fields only.

Fixtures in `tests/test_sources.py` cover malformed configuration, normalization, unknown dates, cancellation, partial results and retry. A read-only live smoke check on 6 November 2026 normalized the first 100 Figma Greenhouse postings and 31 Linear Ashby postings. The Lever public `lever` board returned an empty list; the nonempty Lever mapping is covered by a fictional fixture. No candidate data was transmitted or stored by this check. These observations establish neither ongoing availability nor eligibility.
