# Third-Party Notices

Verified through 2026-08-28. This file records material redistributed from another project, provenance-limited supplied material, and software invoked at runtime. It does not assign a project-wide license to this repository.

## Redistributed upstream material

### No Negative Echo

- Upstream: [LB623/no-negative-echo](https://github.com/LB623/no-negative-echo)
- Inspected revision: `c771b7e6b0bd908c7690e401007a5044cbaf47e0`
- Skill baseline: `9e78138504905bd7c967ce3e2d9ae7cfa2aacdbf`
- License: MIT, Copyright (c) 2026 LB623
- Local scope: `skills/no-negative-echo/`

The upstream license is retained in `skills/no-negative-echo/LICENSE`. `NOTICE.md` and `PROVENANCE.json` in that directory identify adapted, unmodified, original, and omitted files. The upstream-derived skill was reorganized into routine and high-assurance instructions, connected to the research release gate, and given an offline scanner test.

## Supplied material with unresolved upstream provenance

No upstream repository or license accompanied the following files, so this repository does not infer an open-source license for them:

- `skills/supervise-experiment-runs/scripts/build_result_manifest.py`
- `skills/supervise-experiment-runs/scripts/fetch_results.sh`
- `skills/supervise-experiment-runs/scripts/inspect_server.sh`
- `skills/supervise-experiment-runs/scripts/remote_runner.sh`
- `skills/supervise-experiment-runs/scripts/self_test.py`
- `skills/supervise-experiment-runs/scripts/ssh_session.sh`
- `skills/supervise-experiment-runs/scripts/verify_result_manifest.py`
- `skills/revise-evidence-report/assets/report.css`

The supervision scripts were retained and adapted for the current local/SSH interface, result package, failure classification, and offline tests. The stylesheet was mechanically migrated and generalized for the report renderer. Their redistribution terms must be resolved before any public release.

## Runtime software not bundled here

The repository invokes or imports the following software when the corresponding optional capability is used. No source or binary copy of these projects is included.

| Software | Use | Upstream license source |
| --- | --- | --- |
| Matplotlib | Figure rendering | [Matplotlib License](https://github.com/matplotlib/matplotlib/blob/main/LICENSE/LICENSE) |
| NumPy | Numeric arrays and deterministic figure calculations | [BSD 3-Clause license text](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| Pillow | PNG metadata and readability checks | [MIT-CMU license text](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| Pandoc | Markdown-to-HTML/PDF conversion | [GNU GPL version 2 or later](https://github.com/jgm/pandoc/blob/main/COPYING.md) |
| A user-selected TeX/PDF engine | PDF production behind Pandoc | The selected distribution, engine, fonts, and packages retain their own licenses |
| GitHub CLI (`gh`) | Optional read-only adapter for repository, code, issue/PR, commit, and release records | [MIT](https://github.com/cli/cli/blob/trunk/LICENSE) |

GPU drivers, runtimes, compilers, profilers, container engines, SSH clients, and system utilities are discovered or invoked from the execution environment. They are not bundled, and their availability and licensing depend on that environment.

## External collection services and data sources not bundled here

`skills/collect-research-sources/` contains an independently written Python standard-library client and campaign store. It does not redistribute source, containers, Compose files, routes, browser assets, sample full text, or binaries from the services below. Enabling a connector sends caller-approved queries or locators to that service; its current terms, rate limits, privacy behavior, content licenses, and operating cost remain applicable.

| Service or interface | Optional local use | Official license or data-terms source | Integration boundary |
| --- | --- | --- | --- |
| SearXNG | Caller-operated metasearch JSON endpoint | [AGPL-3.0-or-later source license](https://github.com/searxng/searxng/blob/master/LICENSE), [Search API](https://docs.searxng.org/dev/search_api.html) | External discovery service; no server code or deployment stack is included, and underlying search-engine terms still apply |
| RSSHub | Caller-operated RSS/Atom feed producer | [AGPL-3.0 source license](https://github.com/DIYgod/RSSHub/blob/master/LICENSE) | The bundled code is only a generic feed consumer; no RSSHub route or service is included |
| Crossref REST API | DOI and scholarly metadata discovery | [Metadata licensing](https://www.crossref.org/documentation/retrieve-metadata/), [access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/) | Bibliographic facts are broadly reusable, while abstracts may remain copyrighted; abstracts are not retained by the connector |
| OpenAlex API | Scholarly graph and metadata discovery | [CC0 data statement](https://github.com/ourresearch/openalex-docs/blob/main/license.md), [authentication and rate limits](https://help.openalex.org/api/authentication/) | Data records are CC0; API budgets still apply, and linked article files retain their own rights |
| arXiv API | Descriptive metadata and version discovery | [API terms](https://info.arxiv.org/help/api/tou.html), [article license guidance](https://info.arxiv.org/help/license/index.html) | Descriptive metadata is CC0; e-print files are not bundled or downloaded and article redistribution depends on each submission's license |
| PubMed / NCBI E-utilities | Biomedical identifiers and summary metadata | [NCBI policies and copyright guidance](https://www.ncbi.nlm.nih.gov/home/about/policies/), [E-utilities usage requirements](https://www.ncbi.nlm.nih.gov/books/NBK25497/) | PubMed abstracts may be copyrighted and are not collected; users of downstream software must retain the required NCBI disclaimer/copyright notice |
| Europe PMC REST API | Life-science metadata, citation relations, and open-access locators | [Developer access methods](https://europepmc.org/developers), [copyright notice](https://europepmc.org/Copyright) | Full-text and supplementary-content rights vary by article; the connector does not infer reuse permission from a search hit |

On 2026-08-28, pinned SearXNG and RSSHub source installations plus a checksum-verified GitHub CLI release were exercised from the Git-ignored `.runtime/` directory. Those source archives, dependencies, binaries, service configurations, logs, and campaign outputs are local runtime state and are not redistributed by this repository. Exact revisions, checksums, test scope, resource observations, and limitations are recorded in [`docs/third-party-search-runtime.md`](docs/third-party-search-runtime.md).

## Reviewed collection candidates not used as dependencies

The following projects informed interface and risk decisions but are neither bundled nor invoked by the repository:

| Project | Official license/status source | Decision verified through 2026-08-28 |
| --- | --- | --- |
| MediaCrawler | [NON-COMMERCIAL LEARNING LICENSE 1.1](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE), [official repository](https://github.com/NanmiCoder/MediaCrawler) | Not adopted: the license limits purpose and explicitly restricts large-scale crawling; account, cookie, proxy, and platform authorization remain outside this repository |
| Crawl4AI | [repository LICENSE](https://github.com/unclecode/crawl4ai/blob/main/LICENSE), [security advisories](https://github.com/unclecode/crawl4ai/security) | No adapter or code included: the license adds a project-specific attribution requirement after the Apache-2.0 text, and browser/server extraction needs a separately reviewed, pinned, isolated deployment |
| WeWe RSS | [MIT license](https://github.com/cooderl/wewe-rss/blob/main/LICENSE), [archived repository](https://github.com/cooderl/wewe-rss) | Not a deployment dependency: the repository was archived on 2026-05-11 and its account-based workflow has platform/session risk; an already authorized feed may be consumed through the generic RSS interface |
