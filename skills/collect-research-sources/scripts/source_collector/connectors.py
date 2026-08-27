"""Built-in discovery connectors.

Implementations use documented source interfaces and return untrusted records.
They intentionally avoid scientific filtering.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import signal
import subprocess
import threading
import time
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlsplit
import xml.etree.ElementTree as ET

from .model import ConnectorContext, DiscoveryPage, DiscoveryRecord, Query
from .normalize import canonicalize_url
from .security import NetworkError, SafetyError, decode_json


JSON_MIME = {"application/json", "text/json", "application/problem+json"}
XML_MIME = {
    "application/atom+xml",
    "application/rss+xml",
    "application/xml",
    "text/xml",
    "text/plain",
}
TEXT_MIME = JSON_MIME | XML_MIME | {"text/html", "text/plain"}
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=0.5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait(timeout=1)


def _run_bounded(
    argv: list[str],
    *,
    env: dict[str, str],
    timeout_seconds: float,
    max_bytes: int,
) -> tuple[int, bytes]:
    """Capture combined subprocess output with bounded memory and no shell."""
    try:
        process = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=(os.name == "posix"),
        )
    except FileNotFoundError:
        raise NetworkError("gh executable is unavailable") from None
    except OSError as exc:
        raise NetworkError(f"gh launch failed ({type(exc).__name__})") from None

    lock = threading.Lock()
    exceeded = threading.Event()
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    total_seen = 0

    def drain(name: str, stream: Any) -> None:
        nonlocal total_seen
        try:
            while True:
                block = stream.read(16_384)
                if not block:
                    return
                with lock:
                    remaining = max(0, max_bytes - total_seen)
                    if remaining:
                        captured[name].extend(block[:remaining])
                    total_seen += len(block)
                    if total_seen > max_bytes:
                        exceeded.set()
        finally:
            stream.close()

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        if exceeded.is_set():
            _terminate_process(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_process(process)
            break
        time.sleep(0.005)
    for thread in threads:
        thread.join(timeout=1)
    if any(thread.is_alive() for thread in threads):
        _terminate_process(process)
        raise NetworkError("gh output streams did not close")
    if timed_out:
        raise NetworkError("gh request timed out")
    if exceeded.is_set() or total_seen > max_bytes:
        raise SafetyError("gh response exceeds the byte cap")
    return int(process.returncode or 0), bytes(captured["stdout"])


def _cursor_int(cursor: str | None, default: int) -> int:
    if cursor is None:
        return default
    try:
        value = int(cursor)
    except ValueError as exc:
        raise SafetyError("connector cursor is not an integer") from exc
    if value < 0:
        raise SafetyError("connector cursor must not be negative")
    return value


def _environment_value(options: dict[str, Any], field: str) -> str | None:
    name = options.get(field)
    if not name:
        return None
    value = os.environ.get(name)
    if not value:
        label = "credential" if field == "credential_env" else "contact"
        raise NetworkError(f"configured {label} environment variable is unavailable")
    return value


def _secret(options: dict[str, Any]) -> str | None:
    return _environment_value(options, "credential_env")


def _contact(options: dict[str, Any]) -> str | None:
    return _environment_value(options, "contact_env")


def _api_json(
    context: ConnectorContext,
    url: str,
    host: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[Any, int]:
    result = context.http.get(
        url,
        timeout_seconds=context.timeout_seconds,
        max_bytes=context.max_response_bytes,
        allowed_mime_types=JSON_MIME,
        allowed_hosts={host},
        headers=headers,
    )
    return decode_json(result), len(result.body)


def _people(names: Any) -> list[str]:
    output: list[str] = []
    if not isinstance(names, list):
        return output
    for item in names:
        if not isinstance(item, dict):
            continue
        display = item.get("display_name")
        if isinstance(display, str) and display.strip():
            output.append(display.strip())
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            output.append(name.strip())
            continue
        parts = [item.get("given"), item.get("family")]
        joined = " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
        if joined:
            output.append(joined)
    return output


class CrossrefConnector:
    connector_type = "crossref"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        params: dict[str, str] = {
            "query.bibliographic": query.text,
            "rows": str(min(limit, 1000)),
            "select": "DOI,title,author,URL,published,created,type,relation,license,language,publisher",
        }
        if cursor:
            params["cursor"] = cursor
        else:
            params["cursor"] = "*"
        contact = _contact(context.options)
        if contact:
            params["mailto"] = contact
        url = "https://api.crossref.org/works?" + urlencode(params)
        payload, response_bytes = _api_json(context, url, "api.crossref.org")
        message = payload.get("message", {}) if isinstance(payload, dict) else {}
        items = message.get("items", []) if isinstance(message, dict) else []
        records: list[DiscoveryRecord] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            doi = item.get("DOI")
            titles = item.get("title")
            title = titles[0] if isinstance(titles, list) and titles and isinstance(titles[0], str) else None
            records.append(
                DiscoveryRecord(
                    source_id=str(doi or item.get("URL") or title or len(records)),
                    title=title,
                    url=item.get("URL") if isinstance(item.get("URL"), str) else None,
                    external_id=f"doi:{doi}" if isinstance(doi, str) else None,
                    source_owner=item.get("publisher") if isinstance(item.get("publisher"), str) else "Crossref",
                    language=item.get("language") if isinstance(item.get("language"), str) else query.language,
                    mime_type="application/json",
                    http_status=200,
                    content_scope="metadata",
                    access_level="public_metadata_api",
                    relations=_crossref_relations(item),
                    retention_scope="metadata_only",
                    acquisition_method="crossref-rest-api",
                    raw={
                        "DOI": doi,
                        "title": title,
                        "authors": _people(item.get("author")),
                        "type": item.get("type"),
                        "published": item.get("published"),
                        "created": item.get("created"),
                        "license": item.get("license"),
                    },
                    notes=["Crossref abstracts are not retained by the bundled connector."],
                )
            )
        next_cursor = message.get("next-cursor") if isinstance(message, dict) else None
        total = message.get("total-results") if isinstance(message, dict) else None
        return DiscoveryPage(records, str(next_cursor) if next_cursor else None, total if isinstance(total, int) else None, response_bytes)


def _crossref_relations(item: dict[str, Any]) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    relation = item.get("relation")
    if isinstance(relation, dict):
        for kind, values in relation.items():
            for value in values if isinstance(values, list) else []:
                if isinstance(value, dict) and isinstance(value.get("id"), str):
                    relations.append({"kind": str(kind), "target": value["id"], "source": "crossref"})
    relations.extend(
        {"kind": "author", "target": author, "source": "crossref"}
        for author in _people(item.get("author"))
    )
    return relations


def _openalex_abstract(index: Any) -> str | None:
    if not isinstance(index, dict):
        return None
    positions: list[tuple[int, str]] = []
    for token, indexes in index.items():
        if not isinstance(token, str) or not isinstance(indexes, list):
            continue
        for position in indexes:
            if isinstance(position, int) and position >= 0:
                positions.append((position, token))
    if not positions:
        return None
    return " ".join(token for _, token in sorted(positions))


class OpenAlexConnector:
    connector_type = "openalex"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        params = {
            "search": query.text,
            "per-page": str(min(limit, 100)),
            "cursor": cursor or "*",
            "select": "id,doi,title,display_name,publication_date,language,type,authorships,primary_location,abstract_inverted_index,referenced_works,related_works,updated_date",
        }
        api_key = _secret(context.options) if context.options.get("credential_env") else None
        url = "https://api.openalex.org/works?" + urlencode(params)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        payload, response_bytes = _api_json(context, url, "api.openalex.org", headers=headers)
        results = payload.get("results", []) if isinstance(payload, dict) else []
        records: list[DiscoveryRecord] = []
        for item in results if isinstance(results, list) else []:
            if not isinstance(item, dict):
                continue
            location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
            landing = location.get("landing_page_url") if isinstance(location, dict) else None
            source = location.get("source") if isinstance(location, dict) and isinstance(location.get("source"), dict) else {}
            doi = item.get("doi")
            abstract = _openalex_abstract(item.get("abstract_inverted_index"))
            authors = []
            for authorship in item.get("authorships", []) if isinstance(item.get("authorships"), list) else []:
                author = authorship.get("author") if isinstance(authorship, dict) else None
                if isinstance(author, dict) and isinstance(author.get("display_name"), str):
                    authors.append(author["display_name"])
            relations = [
                {"kind": "references", "target": target, "source": "openalex"}
                for target in item.get("referenced_works", []) if isinstance(target, str)
            ]
            relations.extend(
                {"kind": "related", "target": target, "source": "openalex"}
                for target in item.get("related_works", []) if isinstance(target, str)
            )
            relations.extend({"kind": "author", "target": author, "source": "openalex"} for author in authors)
            records.append(
                DiscoveryRecord(
                    source_id=str(item.get("id") or doi or landing or len(records)),
                    title=item.get("title") if isinstance(item.get("title"), str) else item.get("display_name"),
                    url=landing if isinstance(landing, str) else (doi if isinstance(doi, str) else item.get("id")),
                    external_id=doi if isinstance(doi, str) else item.get("id"),
                    source_owner=source.get("display_name") if isinstance(source.get("display_name"), str) else "OpenAlex",
                    language=item.get("language") if isinstance(item.get("language"), str) else query.language,
                    mime_type="application/json",
                    http_status=200,
                    content=abstract,
                    content_scope="abstract" if abstract else "metadata",
                    access_level="public_metadata_api",
                    published_at=item.get("publication_date") if isinstance(item.get("publication_date"), str) else None,
                    updated_at=item.get("updated_date") if isinstance(item.get("updated_date"), str) else None,
                    relations=relations,
                    retention_scope="cc0_metadata",
                    acquisition_method="openalex-api",
                    raw={
                        "id": item.get("id"),
                        "doi": doi,
                        "title": item.get("title"),
                        "authors": authors,
                        "type": item.get("type"),
                        "publication_date": item.get("publication_date"),
                    },
                )
            )
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        next_cursor = meta.get("next_cursor") if isinstance(meta, dict) else None
        total = meta.get("count") if isinstance(meta, dict) else None
        return DiscoveryPage(records, str(next_cursor) if next_cursor else None, total if isinstance(total, int) else None, response_bytes)


class ArxivConnector:
    connector_type = "arxiv"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        start = _cursor_int(cursor, 0)
        params = {
            "search_query": query.text if ":" in query.text else "all:" + query.text,
            "start": str(start),
            "max_results": str(min(limit, 2000)),
            "sortBy": context.options.get("sort_by", "relevance"),
            "sortOrder": context.options.get("sort_order", "descending"),
        }
        url = "https://export.arxiv.org/api/query?" + urlencode(params)
        result = context.http.get(
            url,
            timeout_seconds=context.timeout_seconds,
            max_bytes=context.max_response_bytes,
            allowed_mime_types=XML_MIME,
            allowed_hosts={"export.arxiv.org"},
        )
        try:
            root = ET.fromstring(result.body)
        except ET.ParseError as exc:
            raise NetworkError("arXiv response was not valid Atom XML") from exc
        atom = "{http://www.w3.org/2005/Atom}"
        open_search = "{http://a9.com/-/spec/opensearch/1.1/}"
        records: list[DiscoveryRecord] = []
        for entry in root.findall(atom + "entry"):
            identifier = _xml_text(entry.find(atom + "id"))
            title = _xml_text(entry.find(atom + "title"))
            summary = _xml_text(entry.find(atom + "summary"))
            authors = [_xml_text(author.find(atom + "name")) for author in entry.findall(atom + "author")]
            links = [node.attrib for node in entry.findall(atom + "link")]
            landing = next((link.get("href") for link in links if link.get("rel") == "alternate"), identifier)
            records.append(
                DiscoveryRecord(
                    source_id=identifier or str(len(records)),
                    title=title,
                    url=landing,
                    external_id=identifier,
                    source_owner="arXiv",
                    language=query.language,
                    mime_type="application/atom+xml",
                    http_status=200,
                    content=summary,
                    content_scope="abstract" if summary else "metadata",
                    access_level="public_metadata_api",
                    published_at=_xml_text(entry.find(atom + "published")),
                    updated_at=_xml_text(entry.find(atom + "updated")),
                    retention_scope="cc0_descriptive_metadata",
                    acquisition_method="arxiv-api",
                    raw={"id": identifier, "title": title, "authors": authors, "links": links},
                )
            )
        total_text = _xml_text(root.find(open_search + "totalResults"))
        total = int(total_text) if total_text and total_text.isdigit() else None
        next_cursor = str(start + len(records)) if records and (total is None or start + len(records) < total) else None
        return DiscoveryPage(records, next_cursor, total, len(result.body))


def _xml_text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    text = " ".join("".join(node.itertext()).split())
    return text or None


class EuropePmcConnector:
    connector_type = "europe-pmc"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        params = {
            "query": query.text,
            "format": "json",
            "resultType": "core",
            "pageSize": str(min(limit, 1000)),
        }
        if cursor:
            params["cursorMark"] = cursor
        contact = _contact(context.options)
        if contact:
            params["email"] = contact
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode(params)
        payload, response_bytes = _api_json(context, url, "www.ebi.ac.uk")
        result_list = payload.get("resultList", {}) if isinstance(payload, dict) else {}
        items = result_list.get("result", []) if isinstance(result_list, dict) else []
        retain_text = bool(context.options.get("retain_abstracts", False))
        records: list[DiscoveryRecord] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            doi = item.get("doi")
            pmcid = item.get("pmcid")
            pmid = item.get("pmid")
            external = f"doi:{doi}" if isinstance(doi, str) else (f"pmc:{pmcid}" if pmcid else f"pmid:{pmid}")
            abstract = item.get("abstractText") if retain_text and isinstance(item.get("abstractText"), str) else None
            url_value = f"https://europepmc.org/article/{item.get('source')}/{item.get('id')}"
            relations = []
            if pmcid:
                relations.append({"kind": "has-pmc-record", "target": str(pmcid), "source": "europe-pmc"})
            records.append(
                DiscoveryRecord(
                    source_id=str(item.get("id") or external),
                    title=item.get("title") if isinstance(item.get("title"), str) else None,
                    url=url_value,
                    external_id=external,
                    source_owner="Europe PMC",
                    language=item.get("language") if isinstance(item.get("language"), str) else query.language,
                    mime_type="application/json",
                    http_status=200,
                    content=abstract,
                    content_scope="abstract" if abstract else "metadata",
                    access_level="public_metadata_api",
                    published_at=item.get("firstPublicationDate") if isinstance(item.get("firstPublicationDate"), str) else None,
                    relations=relations,
                    retention_scope="caller_review_required" if abstract else "metadata_only",
                    acquisition_method="europe-pmc-rest-api",
                    raw={
                        "id": item.get("id"),
                        "source": item.get("source"),
                        "doi": doi,
                        "pmcid": pmcid,
                        "pmid": pmid,
                        "title": item.get("title"),
                        "authors": item.get("authorString"),
                        "isOpenAccess": item.get("isOpenAccess"),
                    },
                    notes=[] if retain_text else ["Abstract text was not retained; enable only after reviewing reuse terms."],
                )
            )
        next_cursor = payload.get("nextCursorMark") if isinstance(payload, dict) else None
        total = payload.get("hitCount") if isinstance(payload, dict) else None
        return DiscoveryPage(records, str(next_cursor) if next_cursor else None, total if isinstance(total, int) else None, response_bytes)


class PubmedConnector:
    connector_type = "pubmed"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        start = _cursor_int(cursor, 0)
        base_params = {
            "db": "pubmed",
            "retmode": "json",
            "tool": context.options.get("tool", "research_source_collector"),
        }
        contact = _contact(context.options)
        if contact:
            base_params["email"] = contact
        search_params = dict(base_params)
        search_params.update({"term": query.text, "retstart": str(start), "retmax": str(min(limit, 10000))})
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urlencode(search_params)
        search, first_bytes = _api_json(context, search_url, "eutils.ncbi.nlm.nih.gov")
        search_result = search.get("esearchresult", {}) if isinstance(search, dict) else {}
        ids = search_result.get("idlist", []) if isinstance(search_result, dict) else []
        if not ids:
            total = _as_int(search_result.get("count"))
            return DiscoveryPage([], None, total, first_bytes)
        summary_params = dict(base_params)
        summary_params["id"] = ",".join(str(item) for item in ids)
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urlencode(summary_params)
        summary, second_bytes = _api_json(context, summary_url, "eutils.ncbi.nlm.nih.gov")
        result = summary.get("result", {}) if isinstance(summary, dict) else {}
        records: list[DiscoveryRecord] = []
        for pmid in ids:
            item = result.get(str(pmid), {}) if isinstance(result, dict) else {}
            if not isinstance(item, dict):
                continue
            article_ids = item.get("articleids", [])
            doi = next(
                (entry.get("value") for entry in article_ids if isinstance(entry, dict) and entry.get("idtype") == "doi"),
                None,
            ) if isinstance(article_ids, list) else None
            records.append(
                DiscoveryRecord(
                    source_id=str(pmid),
                    title=item.get("title") if isinstance(item.get("title"), str) else None,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    external_id=f"doi:{doi}" if isinstance(doi, str) else f"pmid:{pmid}",
                    source_owner="NCBI PubMed",
                    language=query.language,
                    mime_type="application/json",
                    http_status=200,
                    content_scope="metadata",
                    access_level="public_metadata_api",
                    published_at=item.get("pubdate") if isinstance(item.get("pubdate"), str) else None,
                    retention_scope="metadata_only",
                    acquisition_method="ncbi-eutilities",
                    raw={
                        "pmid": str(pmid),
                        "doi": doi,
                        "title": item.get("title"),
                        "authors": _people(item.get("authors")),
                        "source": item.get("source"),
                        "pubdate": item.get("pubdate"),
                    },
                    notes=["PubMed abstract text is not collected by this connector."],
                )
            )
        total = _as_int(search_result.get("count"))
        next_cursor = str(start + len(ids)) if total is not None and start + len(ids) < total else None
        return DiscoveryPage(records, next_cursor, total, first_bytes + second_bytes)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class RssConnector:
    connector_type = "rss"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        if cursor:
            return DiscoveryPage([])
        feed_url = context.options.get("feed_url")
        if not isinstance(feed_url, str) or not feed_url:
            raise SafetyError("rss connector requires feed_url")
        host = urlsplit(feed_url).hostname
        if not host:
            raise SafetyError("rss feed URL has no host")
        result = context.http.get(
            feed_url,
            timeout_seconds=context.timeout_seconds,
            max_bytes=context.max_response_bytes,
            allowed_mime_types=XML_MIME,
            allowed_hosts={host.lower()},
            allow_private_hosts=bool(context.options.get("allow_private_hosts", False)),
        )
        try:
            root = ET.fromstring(result.body)
        except ET.ParseError as exc:
            raise NetworkError("feed response was not valid XML") from exc
        retain_text = bool(context.options.get("retain_summaries", False))
        filter_query = bool(context.options.get("filter_query", False))
        terms = [term.casefold() for term in re.findall(r"[\w.-]+", query.text) if len(term) > 1]
        records: list[DiscoveryRecord] = []
        nodes = root.findall(".//item")
        atom = "{http://www.w3.org/2005/Atom}"
        if not nodes and root.tag.endswith("feed"):
            nodes = root.findall(atom + "entry")
        for node in nodes:
            title = _first_xml(node, ["title", atom + "title"])
            summary = _first_xml(node, ["description", "summary", atom + "summary", atom + "content"])
            if filter_query and terms and not any(term in f"{title or ''} {summary or ''}".casefold() for term in terms):
                continue
            link = _first_xml(node, ["link", atom + "link"])
            if not link:
                link_node = node.find(atom + "link")
                link = link_node.attrib.get("href") if link_node is not None else None
            guid = _first_xml(node, ["guid", "id", atom + "id"])
            published = _first_xml(node, ["pubDate", "published", atom + "published", "updated", atom + "updated"])
            content = summary if retain_text else None
            records.append(
                DiscoveryRecord(
                    source_id=guid or link or title or str(len(records)),
                    title=title,
                    url=link,
                    external_id=guid,
                    source_owner=host.lower(),
                    language=query.language,
                    mime_type=result.mime_type,
                    http_status=result.status,
                    content=content,
                    content_scope="discovery_snippet" if content else "metadata",
                    access_level="public_feed",
                    published_at=published,
                    retention_scope="caller_review_required" if content else "metadata_only",
                    acquisition_method="rss-or-atom-feed",
                    raw={"guid": guid, "title": title, "link": link, "published": published},
                    notes=[] if retain_text else ["Feed summary was not retained."],
                )
            )
            if len(records) >= limit:
                break
        return DiscoveryPage(records, None, len(nodes), len(result.body))


def _first_xml(node: ET.Element, names: list[str]) -> str | None:
    for name in names:
        child = node.find(name)
        text = _xml_text(child)
        if text:
            return text
    return None


class SearxngConnector:
    connector_type = "searxng"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        page = _cursor_int(cursor, 1)
        endpoint = context.options.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            raise SafetyError("searxng connector requires endpoint")
        host = urlsplit(endpoint).hostname
        if not host:
            raise SafetyError("SearXNG endpoint has no host")
        params = {"q": query.text, "format": "json", "pageno": str(page)}
        categories = context.options.get("categories")
        if isinstance(categories, list) and categories:
            params["categories"] = ",".join(str(item) for item in categories)
        language = context.options.get("language") or query.language
        if language and language != "und":
            params["language"] = str(language)
        url = endpoint.rstrip("/") + "/search?" + urlencode(params)
        result = context.http.get(
            url,
            timeout_seconds=context.timeout_seconds,
            max_bytes=context.max_response_bytes,
            allowed_mime_types=JSON_MIME,
            allowed_hosts={host.lower()},
            allow_private_hosts=bool(context.options.get("allow_private_hosts", False)),
        )
        payload = decode_json(result)
        items = payload.get("results", []) if isinstance(payload, dict) else []
        retain_text = bool(context.options.get("retain_snippets", False))
        records: list[DiscoveryRecord] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            item_url = item.get("url")
            snippet = item.get("content") if retain_text and isinstance(item.get("content"), str) else None
            engines = item.get("engines") if isinstance(item.get("engines"), list) else []
            records.append(
                DiscoveryRecord(
                    source_id=str(item_url or item.get("title") or len(records)),
                    title=item.get("title") if isinstance(item.get("title"), str) else None,
                    url=item_url if isinstance(item_url, str) else None,
                    source_owner=urlsplit(item_url).hostname if isinstance(item_url, str) else None,
                    language=query.language,
                    mime_type="application/json",
                    http_status=200,
                    content=snippet,
                    content_scope="discovery_snippet" if snippet else "metadata",
                    access_level="metasearch_discovery",
                    retention_scope="caller_review_required" if snippet else "metadata_only",
                    acquisition_method="searxng-search-api",
                    raw={
                        "url": item_url,
                        "title": item.get("title"),
                        "engines": engines,
                        "publishedDate": item.get("publishedDate"),
                    },
                    notes=[] if retain_text else ["Metasearch snippet was not retained."],
                )
            )
            if len(records) >= limit:
                break
        next_cursor = str(page + 1) if len(records) >= limit else None
        return DiscoveryPage(records, next_cursor, None, len(result.body), ["Underlying engine coverage depends on SearXNG configuration."])


class GithubGhConnector:
    connector_type = "github-gh"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        page = _cursor_int(cursor, 1)
        resource = context.options.get("resource", "repositories")
        endpoints = {
            "repositories": "search/repositories",
            "issues": "search/issues",
            "code": "search/code",
            "commits": "search/commits",
        }
        allowed_environment = {
            "PATH", "HOME", "XDG_CONFIG_HOME", "GH_CONFIG_DIR", "GH_HOST", "GH_TOKEN",
            "GH_ENTERPRISE_TOKEN", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY",
            "NO_PROXY", "LANG", "LC_ALL", "NO_COLOR",
        }
        env = {key: value for key, value in os.environ.items() if key in allowed_environment}
        credential_name = context.options.get("credential_env")
        if credential_name:
            token = _secret(context.options)
            if token:
                env["GH_TOKEN"] = token
        if resource == "releases":
            if not GITHUB_REPO_RE.fullmatch(query.text.strip()):
                raise SafetyError("GitHub release query must be an owner/repository slug")
            endpoint = f"repos/{query.text.strip()}/releases"
            argv = ["gh", "api", "--method", "GET", endpoint, "-f", f"per_page={min(limit, 100)}", "-f", f"page={page}"]
        elif resource in endpoints:
            endpoint = endpoints[resource]
            argv = [
                "gh", "api", "--method", "GET", endpoint,
                "-f", f"q={query.text}", "-f", f"per_page={min(limit, 100)}", "-f", f"page={page}",
            ]
        else:
            raise SafetyError("unsupported GitHub resource")
        returncode, stdout = _run_bounded(
            argv,
            env=env,
            timeout_seconds=context.timeout_seconds,
            max_bytes=context.max_response_bytes,
        )
        if returncode != 0:
            raise NetworkError(f"gh request failed with exit status {returncode}")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NetworkError("gh response was not valid UTF-8 JSON") from exc
        items = payload if resource == "releases" else payload.get("items", []) if isinstance(payload, dict) else []
        records: list[DiscoveryRecord] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            record = _github_record(item, resource, query.language)
            records.append(record)
            if len(records) >= limit:
                break
        total = payload.get("total_count") if isinstance(payload, dict) else None
        next_cursor = str(page + 1) if len(records) >= min(limit, 100) else None
        return DiscoveryPage(records, next_cursor, total if isinstance(total, int) else None, len(stdout))


def _github_record(item: dict[str, Any], resource: str, language: str) -> DiscoveryRecord:
    full_name = item.get("full_name")
    owner = full_name.split("/", 1)[0] if isinstance(full_name, str) and "/" in full_name else "GitHub"
    url = item.get("html_url")
    title = item.get("name") or item.get("full_name") or item.get("title") or item.get("path") or item.get("tag_name")
    relations: list[dict[str, Any]] = []
    repository_url = item.get("repository_url")
    repository = item.get("repository")
    if isinstance(repository, dict):
        repository_url = repository.get("html_url") or repository.get("url")
    if isinstance(repository_url, str):
        relations.append({"kind": "belongs-to-repository", "target": repository_url, "source": "github"})
    if resource == "releases" and isinstance(item.get("target_commitish"), str):
        relations.append({"kind": "targets-commitish", "target": item["target_commitish"], "source": "github"})
    return DiscoveryRecord(
        source_id=str(item.get("node_id") or item.get("id") or url or title),
        title=str(title) if title is not None else None,
        url=url if isinstance(url, str) else None,
        external_id=str(item.get("node_id")) if item.get("node_id") else None,
        source_owner=owner,
        language=item.get("language") if isinstance(item.get("language"), str) else language,
        mime_type="application/json",
        http_status=200,
        content_scope="metadata",
        access_level="github-api-record",
        published_at=item.get("created_at") or item.get("published_at"),
        updated_at=item.get("updated_at"),
        version=item.get("sha") or item.get("tag_name"),
        relations=relations,
        retention_scope="metadata_only",
        acquisition_method="github-gh-api",
        raw={
            "id": item.get("id"),
            "node_id": item.get("node_id"),
            "url": url,
            "title": title,
            "state": item.get("state"),
            "sha": item.get("sha"),
            "tag_name": item.get("tag_name"),
        },
        notes=["Bodies and comments are not retained by the bundled connector."],
    )


class WebSeedConnector:
    connector_type = "web-seed"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        start = _cursor_int(cursor, 0)
        seeds = context.options.get("seeds", [])
        if not isinstance(seeds, list):
            raise SafetyError("web-seed connector requires a seeds list")
        selected = seeds[start : start + limit]
        records: list[DiscoveryRecord] = []
        for index, seed in enumerate(selected, start=start):
            if isinstance(seed, str):
                seed = {"url": seed}
            if not isinstance(seed, dict) or not isinstance(seed.get("url"), str):
                raise SafetyError(f"invalid web seed at index {index}")
            canonical_url = canonicalize_url(seed["url"])
            if canonical_url is None:
                raise SafetyError(
                    f"web seed at index {index} must be a canonicalizable HTTP(S) URL "
                    "without embedded credentials"
                )
            records.append(
                DiscoveryRecord(
                    source_id=str(seed.get("id") or canonical_url),
                    title=seed.get("title") if isinstance(seed.get("title"), str) else None,
                    url=canonical_url,
                    external_id=seed.get("external_id") if isinstance(seed.get("external_id"), str) else None,
                    source_owner=seed.get("source_owner") if isinstance(seed.get("source_owner"), str) else urlsplit(canonical_url).hostname,
                    language=seed.get("language") if isinstance(seed.get("language"), str) else query.language,
                    content_scope="metadata",
                    access_level="caller_supplied_locator",
                    retention_scope="metadata_only",
                    acquisition_method="caller-supplied-seed",
                    raw={"seed_index": index, "url": canonical_url, "title": seed.get("title")},
                )
            )
        next_cursor = str(start + len(selected)) if start + len(selected) < len(seeds) else None
        return DiscoveryPage(records, next_cursor, len(seeds), 0)


class FixtureConnector:
    connector_type = "fixture"

    def discover(self, query: Query, cursor: str | None, limit: int, context: ConnectorContext) -> DiscoveryPage:
        if not context.options.get("test_only"):
            raise SafetyError("fixture connector requires test_only=true")
        if context.options.get("fail"):
            raise NetworkError(str(context.options.get("failure_label", "fixture connector failure"))[:200])
        page = _cursor_int(cursor, 0)
        pages = context.options.get("pages", [])
        if not isinstance(pages, list) or page >= len(pages):
            return DiscoveryPage([])
        page_records = pages[page]
        if not isinstance(page_records, list):
            raise SafetyError("fixture page must be a list")
        records: list[DiscoveryRecord] = []
        for index, item in enumerate(page_records[:limit]):
            if not isinstance(item, dict):
                raise SafetyError("fixture record must be an object")
            records.append(
                DiscoveryRecord(
                    source_id=str(item.get("source_id", f"{page}-{index}")),
                    title=item.get("title"),
                    url=item.get("url"),
                    external_id=item.get("external_id"),
                    source_owner=item.get("source_owner", "fixture-owner"),
                    language=item.get("language", query.language),
                    mime_type=item.get("mime_type", "application/json"),
                    http_status=item.get("http_status", 200),
                    content=item.get("content"),
                    content_scope=item.get("content_scope", "metadata"),
                    access_level=item.get("access_level", "fixture"),
                    published_at=item.get("published_at"),
                    updated_at=item.get("updated_at"),
                    version=item.get("version"),
                    relations=item.get("relations", []),
                    retention_scope=item.get("retention_scope", "test_fixture"),
                    acquisition_method="offline-fixture",
                    raw=item,
                    notes=item.get("notes", []),
                )
            )
        next_cursor = str(page + 1) if page + 1 < len(pages) else None
        response_bytes = len(json.dumps(page_records, ensure_ascii=False).encode("utf-8"))
        return DiscoveryPage(records, next_cursor, sum(len(p) for p in pages if isinstance(p, list)), response_bytes)


CONNECTOR_FACTORIES: dict[str, Callable[[], Any]] = {
    connector.connector_type: connector
    for connector in (
        CrossrefConnector,
        OpenAlexConnector,
        ArxivConnector,
        EuropePmcConnector,
        PubmedConnector,
        RssConnector,
        SearxngConnector,
        GithubGhConnector,
        WebSeedConnector,
        FixtureConnector,
    )
}


def register_connector(connector_type: str, factory: Callable[[], Any]) -> None:
    """Register a trusted in-process connector without changing campaign semantics."""

    if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", connector_type):
        raise ValueError("connector type must be lowercase-hyphen form")
    if connector_type in CONNECTOR_FACTORIES:
        raise ValueError(f"connector type is already registered: {connector_type}")
    instance = factory()
    if getattr(instance, "connector_type", None) != connector_type or not callable(getattr(instance, "discover", None)):
        raise ValueError("connector factory does not implement the declared interface")
    CONNECTOR_FACTORIES[connector_type] = factory


def create_connector(connector_type: str):  # type: ignore[no-untyped-def]
    factory = CONNECTOR_FACTORIES.get(connector_type)
    if factory is None:
        raise SafetyError(f"unknown connector type: {connector_type}")
    return factory()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
