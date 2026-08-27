"""Network and configuration safety controls for untrusted collection."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .normalize import canonicalize_url


SECRET_KEY_RE = re.compile(
    r"(?:^|[_-])(?:token|secret|password|passwd|cookie|api[_-]?key|access[_-]?key|private[_-]?key|"
    r"credential|authorization|auth|bearer|session|proxy[_-]?url)(?:$|[_-])",
    re.I,
)
SAFE_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


class SafetyError(RuntimeError):
    """A request or configuration violated a mechanical safety boundary."""


class NetworkError(RuntimeError):
    """A sanitized network failure."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def find_secret_shaped_config(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in {"credential_env", "contact_env"}:
                if not isinstance(child, str) or not SAFE_ENV_NAME_RE.fullmatch(child):
                    findings.append(f"{child_path} must be an environment-variable name")
                continue
            if SECRET_KEY_RE.search(str(key)):
                findings.append(f"{child_path} is a secret-shaped configuration field")
            findings.extend(find_secret_shaped_config(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_secret_shaped_config(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        parsed = urlsplit(value)
        if parsed.scheme and (parsed.username is not None or parsed.password is not None):
            findings.append(f"{path} contains URL user information")
        if parsed.scheme and any(SECRET_KEY_RE.search(key) for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            findings.append(f"{path} contains a secret-shaped URL query parameter")
    return findings


def _unsafe_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return any(
        (
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_remote_url(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    allow_private_hosts: bool = False,
    resolver=socket.getaddrinfo,
) -> str:
    canonical = canonicalize_url(url)
    if canonical is None:
        raise SafetyError("URL must be canonicalizable HTTP(S) without embedded credentials")
    parsed = urlsplit(canonical)
    host = parsed.hostname or ""
    if allowed_hosts is not None and host not in allowed_hosts:
        raise SafetyError("host is outside the explicit allowlist")
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = {item[4][0] for item in resolver(host, parsed.port or default_port, type=socket.SOCK_STREAM)}
    except (OSError, UnicodeError) as exc:
        raise SafetyError("host resolution failed") from exc
    if not addresses:
        raise SafetyError("host resolution returned no address")
    if not allow_private_hosts and any(_unsafe_ip(address) for address in addresses):
        raise SafetyError("host resolves to a non-public address")
    return canonical


@dataclass
class HttpResult:
    final_url: str
    status: int
    mime_type: str
    body: bytes
    headers: dict[str, str]


class SafeHttpClient:
    """Size-bounded HTTP client that validates each redirect."""

    def __init__(self, user_agent: str = "research-source-collector/1.0") -> None:
        self.user_agent = user_agent
        self._opener = build_opener(_NoRedirect())

    def get(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        allowed_mime_types: set[str],
        allowed_hosts: set[str] | None,
        allow_private_hosts: bool = False,
        headers: dict[str, str] | None = None,
        max_redirects: int = 5,
    ) -> HttpResult:
        current = url
        request_headers = {
            "Accept-Encoding": "identity",
            "User-Agent": self.user_agent,
        }
        if headers:
            request_headers.update(headers)
        for _ in range(max_redirects + 1):
            current = validate_remote_url(
                current,
                allowed_hosts=allowed_hosts,
                allow_private_hosts=allow_private_hosts,
            )
            request = Request(current, headers=request_headers, method="GET")
            try:
                response = self._opener.open(request, timeout=timeout_seconds)
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    location = exc.headers.get("Location")
                    if not location:
                        raise NetworkError(f"redirect status {exc.code} had no location") from None
                    current = urljoin(current, location)
                    continue
                raise NetworkError(f"HTTP status {exc.code}") from None
            except (URLError, TimeoutError, OSError) as exc:
                reason = type(getattr(exc, "reason", exc)).__name__
                raise NetworkError(f"network request failed ({reason})") from None
            with response:
                status = int(getattr(response, "status", 200))
                encoding = (response.headers.get("Content-Encoding") or "identity").lower()
                if encoding not in {"", "identity"}:
                    raise SafetyError("compressed response bodies are not accepted")
                declared = response.headers.get("Content-Length")
                if declared:
                    try:
                        if int(declared) > max_bytes:
                            raise SafetyError("declared response size exceeds the byte cap")
                    except ValueError:
                        raise SafetyError("invalid Content-Length") from None
                content_type = (response.headers.get_content_type() or "application/octet-stream").lower()
                if content_type not in allowed_mime_types:
                    raise SafetyError(f"MIME type is not allowed: {content_type}")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise SafetyError("response body exceeds the byte cap")
                selected_headers = {
                    key.lower(): value
                    for key, value in response.headers.items()
                    if key.lower() in {
                        "content-type",
                        "content-length",
                        "etag",
                        "last-modified",
                        "retry-after",
                        "x-rate-limit-limit",
                        "x-rate-limit-interval",
                        "x-ratelimit-limit",
                        "x-ratelimit-remaining",
                        "x-ratelimit-reset",
                    }
                }
                return HttpResult(current, status, content_type, body, selected_headers)
        raise SafetyError("redirect limit exceeded")


def decode_json(result: HttpResult) -> Any:
    try:
        return json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError("response was not valid UTF-8 JSON") from exc
