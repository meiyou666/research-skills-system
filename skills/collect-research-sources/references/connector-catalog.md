# Connector Catalog and Adoption Decisions

Verified through 2026-08-28 from the official pages linked below. The machine-readable runtime view is [`connector_profiles.json`](connector_profiles.json). Service limits and terms can change; recheck them before a large or authenticated campaign.

## Bundled scholarly connectors

### Crossref — adopted

- Official interface: <https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/>
- Large-query guidance: <https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/>
- Access: public API requires no signup; the polite pool identifies a contact; paid Metadata Plus is outside the default path.
- Constraints: follow response rate/concurrency headers, cache results, back off on `429`, and prefer public snapshots for bulk extraction. Most metadata is reusable, but publisher abstracts can carry copyright.
- Implementation: bundled standard-library query/cursor adapter. It retains selected metadata and relations, not abstracts. A failure is isolated to its task.

### OpenAlex — adopted with budget-aware authentication

- Official API overview: <https://help.openalex.org/api/>
- Authentication and pricing: <https://help.openalex.org/api/authentication/>, <https://help.openalex.org/access/pricing/>
- Terms: <https://openalex.org/OpenAlex_termsofservice.pdf>
- Access: the data is CC0. The API is a metered service; scalable use requires a free caller-owned key, daily credits apply, and bulk work may fit the snapshot better.
- Implementation: bundled standard-library cursor adapter for works, DOI identities, references, related works, authors, and reconstructed abstracts. The key is read only from a named environment variable and sent in the documented bearer authorization header.

### arXiv — adopted for metadata

- API access: <https://info.arxiv.org/help/api/index.html>
- API manual: <https://info.arxiv.org/help/api/user-manual.html>
- API terms: <https://info.arxiv.org/help/api/tou.html>
- Access: no authentication. Legacy API users must use one connection and at most one request per three seconds. Descriptive metadata is CC0; e-print redistribution depends on the work's license. arXiv requests acknowledgement and prohibits implied endorsement.
- Implementation: bundled Atom parser with version-preserving identity. It does not download or redistribute e-print files.

### Europe PMC — adopted

- Developer resources: <https://europepmc.org/developers>
- REST API: <https://europepmc.org/RestfulWebService>
- Open-access subset: <https://europepmc.org/downloads/openaccess>
- Access: public REST search provides metadata, identifiers, citations, references, and open-access locators. Full-text reuse follows the license attached to each article.
- Implementation: bundled cursor adapter. Abstract retention is disabled unless the caller explicitly accepts its retention basis; open-access status remains metadata, not permission inferred by the collector.

### PubMed / NCBI E-utilities — adopted

- Official API hub: <https://www.ncbi.nlm.nih.gov/home/develop/api/>
- Usage requirements: <https://www.ncbi.nlm.nih.gov/books/NBK25497/>
- Parameter reference: <https://www.ncbi.nlm.nih.gov/books/NBK25499/>
- Access: the bundled path stays without a key and at or below three requests per second. A separate caller may use NCBI's documented key tier after reviewing how the key is transmitted. Supply optional contact identity through `contact_env`; use Entrez History/batches for large retrieval, and display the NCBI disclaimer/copyright notice. PubMed abstracts may be copyrighted.
- Implementation: bounded ESearch→ESummary adapter. It stores PMID/DOI and summary metadata, not abstracts or API keys.

## Discovery, feed, and repository connectors

### SearXNG — optional external discovery service

- Official repository and license: <https://github.com/searxng/searxng>, <https://github.com/searxng/searxng/blob/master/LICENSE>
- Search API: <https://docs.searxng.org/dev/search_api.html>
- Container deployment: <https://docs.searxng.org/admin/installation-docker.html>
- Limiter: <https://docs.searxng.org/admin/searx.limiter.html>
- Decision: use only as a caller-operated, bounded discovery fan-out. SearXNG is AGPL-3.0-or-later, self-hosting has service/cache cost, JSON output may be disabled, and underlying engine rules still apply. No SearXNG code or deployment stack is bundled.

The connector needs an endpoint, supports language/category/page parameters, and records returned engines. A private endpoint requires the caller to enable private-host access explicitly; network egress controls remain recommended.

### RSS, RSSHub, and WeWe RSS — generic RSS adopted; providers remain external

- RSSHub repository/license/deployment: <https://github.com/DIYgod/RSSHub>, <https://github.com/DIYgod/RSSHub/blob/master/LICENSE>, <https://docs.rsshub.app/deploy/>
- WeWe RSS repository/license: <https://github.com/cooderl/wewe-rss>, <https://github.com/cooderl/wewe-rss/blob/main/LICENSE>
- Decision: bundle a generic RSS/Atom consumer and incremental-refresh path. RSSHub is an optional caller-operated AGPL-3.0 service; route credentials, target-platform rules, caching, and compute remain with its operator. WeWe RSS is MIT but its repository was archived on 2026-05-11 and its account-based WeChat workflow has account-control risk, so it is not a recommended deployment dependency. An already authorized caller-owned feed can still be consumed.

Feed summaries are not retained by default. A feed item remains a discovery record until the source-owning artifact is reviewed.

### GitHub `gh` CLI — optional adapter adopted

- Official repository/license: <https://github.com/cli/cli>, <https://github.com/cli/cli/blob/trunk/LICENSE>
- API manual: <https://cli.github.com/manual/gh_api>
- Authentication manual: <https://cli.github.com/manual/gh_auth_login>
- API rate limits: <https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>
- Decision: use a caller-installed `gh` for bounded repository, code, issue/PR, commit, and release records. The CLI is MIT. The adapter uses existing auth state or an environment-injected token, never calls login, and never places tokens in arguments. Repository content retains its own license; private records require explicit scope and sharing review.

## Page extraction and social-platform candidates

### Crawl4AI — optional external extractor, no bundled adapter

- Official repository: <https://github.com/unclecode/crawl4ai>
- Official documentation: <https://docs.crawl4ai.com/>
- Repository license: <https://github.com/unclecode/crawl4ai/blob/main/LICENSE>
- Decision: consider only for a controlled external page-extraction profile after version, health, JWT, egress, browser, and target-host policy checks. The current repository license contains Apache License 2.0 text plus an additional attribution requirement; no code is copied here. Browser execution, JavaScript hooks, local-file features, and a history of security fixes raise the isolation and resource cost above the standard-library fetcher.

The bundled generic fetcher is intentionally text-only, robots-aware, host-allowlisted, size-bounded, and unable to execute JavaScript. It labels HTML extraction `partial_content`. If Crawl4AI is later adapted, send only prevalidated HTTP(S) URLs, disable local-file and arbitrary-hook surfaces, pin a reviewed release, and keep extracted text untrusted.

### MediaCrawler — not adopted

- Official repository: <https://github.com/NanmiCoder/MediaCrawler>
- Official license: <https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE>
- Decision: the `NON-COMMERCIAL LEARNING LICENSE 1.1` limits use to non-commercial learning/research and explicitly restricts large-scale crawling and platform disruption. Its browser/QR-login, cookie/session, proxy, and social-platform automation paths carry account, privacy, terms, and operational risk. That conflicts with a reusable large-campaign core.

Do not invoke it through this skill. A caller may separately assess a narrowly authorized use, the then-current license, account ownership, target-platform terms, and retention policy; such an external action remains explicit opt-in and outside the bundled connector registry.

## Actual test boundary

The hermetic suite exercises canonicalization, DOI/GitHub/arXiv identities, dedupe, version clusters, mixed Chinese/English queries, multi-page resume, incremental refresh, failure isolation, lifecycle/outcome separation, rate limiting, content hashes, snapshots, prompt-injection payloads, unsafe schemes/addresses, MIME/size/content-encoding limits, header-only credential handling, credential rejection, and tamper detection. It directly parses an offline Atom feed.

A fresh forward harness also exercised 606 mixed-language candidates, bounded interruption and resume, strict concurrent discovery/fetch response budgets, package-watermark reporting, six simulated `gh` resource paths, loopback Atom refresh, relation expansion, partial content, a single failed connector, an all-failed campaign, and manifest/snapshot/SQLite tampering. These are interface and state tests, not evidence of live API compatibility or million-record performance.

Crossref and OpenAlex each received one explicitly enabled three-item online attempt on 2026-08-27. Both campaign packages and validators completed, but the endpoints returned no records because this execution environment ended the connections (`SSLEOFError` and `ConnectionResetError`). This is recorded as an access gap, not a core self-test failure. On 2026-08-28, an authenticated, checksum-verified `gh 2.98.0` binary returned three bounded repository candidates through the real connector; a pinned RSSHub build reached its configured five-candidate limit on the official local test route and reported `limited` / `candidates_with_gaps`; and a pinned SearXNG instance passed health, JSON, connector, and package validation while its attempted upstream engines all failed or timed out, yielding zero candidates. arXiv, Europe PMC, and PubMed remain offline-fixture-only here. Details and runtime boundaries are in [`../../../docs/third-party-search-runtime.md`](../../../docs/third-party-search-runtime.md). No claim of exhaustive source or literature coverage is made.
