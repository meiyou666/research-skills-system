"""Canonical identifiers, URLs, and version clusters."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref_src",
}
TRACKING_PREFIXES = ("utm_",)
DOI_RE = re.compile(r"(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)", re.I)
ARXIV_RE = re.compile(r"(?:arxiv:|https?://arxiv\.org/(?:abs|pdf)/)?([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?$", re.I)
GITHUB_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+?)(?:\.git)?(?:/(issues|pull)/([0-9]+)|/commit/([0-9a-f]{7,40})|/releases/tag/([^/#?]+))?/?$",
    re.I,
)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = DOI_RE.search(value.strip())
    if not match:
        return None
    doi = match.group(1).rstrip(".,;:)]}").lower()
    return doi if "/" in doi else None


def normalize_arxiv(value: str | None) -> tuple[str, str | None] | None:
    if not value:
        return None
    clean = value.strip().split("?", 1)[0].split("#", 1)[0]
    match = ARXIV_RE.fullmatch(clean)
    if not match:
        return None
    return match.group(1).lower(), match.group(2).lower() if match.group(2) else None


def canonicalize_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    scheme = parsed.scheme.lower()
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    raw_path = parsed.path or "/"
    normalized_path = posixpath.normpath(raw_path)
    if raw_path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    path = quote(normalized_path, safe="/%:@!$&'()*+,;=-._~")
    pairs = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_KEYS or lowered.startswith(TRACKING_PREFIXES):
            continue
        pairs.append((key, item))
    query = urlencode(sorted(pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def identify(external_id: str | None, url: str | None) -> dict[str, str | None]:
    """Return canonical key, URL, external ID, version, and cluster."""

    doi = normalize_doi(external_id) or normalize_doi(url)
    if doi:
        return {
            "canonical_key": f"doi:{doi}",
            "canonical_url": f"https://doi.org/{doi}",
            "external_id": f"doi:{doi}",
            "version": None,
            "version_cluster": f"doi:{doi}",
        }
    arxiv = normalize_arxiv(external_id) or normalize_arxiv(url)
    if arxiv:
        base, version = arxiv
        suffix = version or ""
        return {
            "canonical_key": f"arxiv:{base}{suffix}",
            "canonical_url": f"https://arxiv.org/abs/{base}{suffix}",
            "external_id": f"arxiv:{base}{suffix}",
            "version": version,
            "version_cluster": f"arxiv:{base}",
        }
    canonical = canonicalize_url(url)
    if canonical:
        github = GITHUB_RE.match(canonical)
        if github:
            owner, repo, kind, number, commit, tag = github.groups()
            repo = repo.removesuffix(".git")
            root = f"github:{owner.lower()}/{repo.lower()}"
            if kind and number:
                suffix = "pull" if kind == "pull" else "issue"
                key = f"{root}:{suffix}:{number}"
                cluster = key
            elif commit:
                key = f"{root}:commit:{commit.lower()}"
                cluster = root
            elif tag:
                key = f"{root}:release:{tag}"
                cluster = root
            else:
                key = root
                cluster = root
            return {
                "canonical_key": key,
                "canonical_url": canonical,
                "external_id": external_id or key,
                "version": commit or tag,
                "version_cluster": cluster,
            }
        return {
            "canonical_key": f"url:{canonical}",
            "canonical_url": canonical,
            "external_id": external_id,
            "version": None,
            "version_cluster": f"url:{canonical}",
        }
    if external_id:
        clean = " ".join(external_id.strip().split()).lower()
        return {
            "canonical_key": f"id:{clean}",
            "canonical_url": None,
            "external_id": external_id,
            "version": None,
            "version_cluster": f"id:{clean}",
        }
    return {
        "canonical_key": "record:" + sha256_text(stable_json({"url": url, "external_id": external_id})),
        "canonical_url": canonical,
        "external_id": external_id,
        "version": None,
        "version_cluster": None,
    }


def candidate_id(canonical_key: str) -> str:
    return "candidate-" + sha256_text(canonical_key)[:24]
