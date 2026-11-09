# Discovery sources

Open Vitæ selects sources locally from explicit search roles, locations, optional two-letter search country codes and work arrangement. No model, identity, CV, contact information, demographic inference or eligibility inference is used. Unknown professions keep general sources. Unknown countries keep broad regional coverage; a city alone is not converted into a country. Optional country codes cover ISO 3166-1 alpha-2 countries; named-location recognition currently covers France, UK, Germany, Spain, Belgium, US, Canada, Sweden and Norway.

Settings → Job sources shows every source, its access limitations, selection reason and **Automatic / Enabled / Disabled** choice. Automatic selection updates with the profile; explicit choices persist. An enabled external source remains an external link, never an automatic import. Saved jobs and employer boards survive preference changes. The catalogue is bundled and versioned in `source_catalog.py`, with review date, countries, professional categories, work arrangements, attribution and documentation links.

## Catalogue (reviewed 9 November 2026)

| Source | Access and coverage | Limits / attribution |
|---|---|---|
| Arbeitnow Europe / UK | Public JSON; European or UK search preferences | General feeds, not exhaustive national coverage |
| Himalayas | Public search; remote or flexible preferences | Professional role query and optional country; remote eligibility still needs checking |
| [Remotive](https://github.com/remotive-com/remote-jobs-api) | Public JSON; remote or flexible | Listings delayed 24 hours; retain Remotive name and listing link; at most four attempts/day |
| [Remote OK](https://remoteok.com/faq) | Public JSON; remote or flexible | Credit Remote OK and retain original listing links |
| [Jobicy](https://jobicy.com/jobs-rss-feed) | Public JSON; remote or flexible | Only last seven days; original links and attribution; at most one new attempt/hour, including changed queries |
| [We Work Remotely](https://weworkremotely.com/remote-job-rss-feed) | Public RSS; remote or flexible | Official feed page explicitly permits use with attribution and links back; local role mapping chooses a category, otherwise the general feed |
| [JobSearch Sweden](https://jobsearch.api.jobtechdev.se/) | External search for Sweden | API qualification incomplete; not enabled as an import |
| [EURAXESS](https://euraxess.ec.europa.eu/jobs/search), [jobs.ac.uk](https://www.jobs.ac.uk/search/) | External research/academic searches | No current import contract verified |
| [ReliefWeb](https://apidoc.reliefweb.int/) | External humanitarian/NGO search | API requires a pre-approved appname |
| [NAV Norway](https://navikt.github.io/pam-stilling-feed/) | External Norwegian search | Production feed access requires prior agreement |
| [France Travail](https://www.data.gouv.fr/dataservices/api-offres-demploi) | External French search | Official catalogue says API is not currently exposed for unrestricted new integrations |
| [Adzuna](https://developer.adzuna.com/), [USAJOBS](https://developer.usajobs.gov/api-reference/job-apis) | External searches | API keys required; excluded from automatic imports |
| The Muse | External search | Historical API documentation redirects; no operational connector claimed |

External links open the source's search page in the browser. There is no background request or automatic transfer of profile criteria to these sites. Offers from external sites can still be added manually. Free public feeds mainly improve remote coverage; they do not cover every country or profession.

## Employer boards

Settings accepts at most six boards: `greenhouse:slug`, `lever:slug`, `lever-eu:slug`, `ashby:slug` or `smartrecruiters:slug`. Use the identifier from the employer's official careers link, never a candidate name or email. No guessed employers are silently added. Board identifiers are not claims about legal company names. Review employer and provider terms before configuring a board.

Official contracts: [Greenhouse](https://docs.greenhouse.io/job-board), [Lever](https://github.com/lever/postings-api), [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api), [SmartRecruiters](https://developers.smartrecruiters.com/docs/endpoints). SmartRecruiters reads only the public company list; missing descriptions remain missing, with no per-job fan-out. Greenhouse `updated_at` is not publication time, Lever does not guarantee an original publication date, and unlisted Ashby entries are ignored. Dates without a timezone stay unknown.

## Bounds, privacy and caching

Each refresh makes at most one read per selected catalogue import (seven maximum), plus six configured boards. Each HTTPS read is capped at 3 MB, with a 15-second socket timeout; each source contributes at most 100 rows. There is no pagination. A visible notice identifies responses reaching the cap or advertising more results. The recommendations view still shows the twelve highest-ranked offers.

Himalayas rotates through every role/country combination, one per uncached search cycle. Jobicy uses the selected role as a keyword (maximum 50 characters), without guessed geography/category taxonomy slugs. WWR rotates through supported categories matched by explicit local role terms. An explicit search query replaces profile roles for that refresh. Successful identical aggregate searches are reused for 24 hours, so profile-based rotation normally advances daily. Partial failures retain the same rotation for retries during that 24-hour cycle, then advance so an unavailable source cannot indefinitely stall other criteria.

A bounded cache of at most 200 successful source/endpoint reads lasts 24 hours. It stores timestamps and truncation status, not raw source responses; imported listings already persist locally. Partial failures retry only unsuccessful or uncached endpoints. Cancellation does not cache an incompletely processed response. Remotive and Jobicy attempt timestamps survive restart and apply source-wide even after failure or query changes; skipped rate-limited reads are reported separately. No automatic retry is scheduled.

The existing public-address/DNS-pinned HTTPS client validates redirects and rejects private networks. RSS uses the same bounded client; declarations/entities are rejected and HTML is reduced to text. No credentials, scraping, CAPTCHA solving or submission POSTs are introduced. Job sources receive only professional query terms and optional country filtering, never CV or contact data. Broad Remotive/Remote OK reads transmit no profile terms. Cancellation is cooperative between source reads and rows; an in-flight read completes first.

Original source listing links and visible attribution are retained. Identity uses canonical listing URLs; different aggregator and ATS URLs for the same role may still duplicate. Saved dossiers are not overwritten; missing rows do not imply closure. Existing 45-day feed age checks and Himalayas expiry checks remain. Salary affects ranking and existing explicit strict constraints, never source selection. Unknown conditions remain visible for review.

## Local API and compatibility

`GET /api/sources` retains `boards`, and adds `catalog_version`, `catalog` (capabilities, preference, selected state, reason), and `preferences`. `PUT /api/sources` accepts `boards` and/or a complete `preferences` object keyed by known source ID with `auto`, `on` or `off`. Omitted top-level fields are preserved; omitted source preferences default to automatic. Validation occurs before saving. Existing local token requirements remain.

The profile adds optional `search_countries` (up to ten distinct uppercase ISO codes); older profiles default to none and older clients omitting the field preserve its saved value. Discovery results add `cached_sources`, `limited_sources`, `truncated` and `completed`. Recommendations add selected `external_sources`.

Fixtures cover selection, all explicit role/country combinations, malformed feeds, unknown dates, attribution, cancellation, partial retries, source-wide limits, backwards compatibility and API validation. Documentation review is not proof that a live endpoint is continuously available. No real candidate data or provider account is used in tests.

A read-only live smoke check on 9 November 2026 normalized 13 Remotive, 99 Remote OK, 100 Jobicy and 100 WWR postings, plus one posting from the public SmartRecruiters company board. All normalized rows had the required URL, title and company fields. Jobicy and WWR reached the collection cap. No candidate profile was transmitted and no live listings were stored. These observations do not guarantee continuing availability or eligibility.
