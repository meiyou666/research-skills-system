"""Robots-aware, text-only generic page acquisition."""

from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .security import NetworkError, SafeHttpClient, SafetyError


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs):  # type: ignore[no-untyped-def]
        if tag.lower() in {"script", "style", "noscript", "template", "svg"}:
            self.skip_depth += 1
        elif not self.skip_depth and tag.lower() in {"p", "div", "section", "article", "h1", "h2", "h3", "li", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "template", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag.lower() in {"p", "div", "section", "article", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts)
        value = re.sub(r"[ \t\f\v]+", " ", value)
        value = re.sub(r"\n\s*\n+", "\n\n", value)
        return value.strip()


class PageFetcher:
    def __init__(self, http: SafeHttpClient, user_agent: str) -> None:
        self.http = http
        self.user_agent = user_agent
        self._robots: dict[
            tuple[str, int | None, str],
            tuple[RobotFileParser | None, int],
        ] = {}

    def fetch(
        self,
        url: str,
        *,
        allowed_hosts: set[str],
        allow_private_hosts: bool,
        allowed_mime_types: set[str],
        robots_unavailable: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> tuple[str, str, int, int]:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if host not in allowed_hosts:
            raise SafetyError("page host is outside the explicit fetch allowlist")
        robots_key = (parsed.scheme, parsed.port, host)
        robots, robots_bytes = self._robots_for(
            parsed.scheme,
            host,
            parsed.port,
            allowed_hosts,
            allow_private_hosts,
            timeout_seconds,
            min(max_bytes, 512_000),
            robots_unavailable,
        )
        if robots is not None and not robots.can_fetch(self.user_agent, url):
            raise SafetyError("robots policy disallows this page")
        remaining_bytes = max_bytes - robots_bytes
        if remaining_bytes <= 0:
            raise SafetyError("robots response exhausted the page-fetch byte budget")
        result = self.http.get(
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=remaining_bytes,
            allowed_mime_types=allowed_mime_types,
            allowed_hosts=allowed_hosts,
            allow_private_hosts=allow_private_hosts,
        )
        if len(result.body) > remaining_bytes:
            raise SafetyError("response body exceeds the byte cap")
        charset = "utf-8"
        content_type = result.headers.get("content-type", "")
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.I)
        if match:
            charset = match.group(1)
        try:
            decoded = result.body.decode(charset)
        except (LookupError, UnicodeDecodeError) as exc:
            raise SafetyError("page is not decodable text") from exc
        if result.mime_type == "text/html":
            parser = _TextExtractor()
            parser.feed(decoded)
            text = parser.text()
        else:
            text = decoded.strip()
        if not text:
            raise NetworkError("page extraction produced no text")
        self._robots[robots_key] = (robots, 0)
        return text, result.mime_type, result.status, robots_bytes + len(result.body)

    def _robots_for(
        self,
        scheme: str,
        host: str,
        port: int | None,
        allowed_hosts: set[str],
        allow_private_hosts: bool,
        timeout_seconds: float,
        max_bytes: int,
        unavailable_policy: str,
    ) -> tuple[RobotFileParser | None, int]:
        key = (scheme, port, host)
        if key in self._robots:
            return self._robots[key]
        netloc = host if port is None else f"{host}:{port}"
        robots_url = urlunsplit((scheme, netloc, "/robots.txt", "", ""))
        try:
            result = self.http.get(
                robots_url,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
                allowed_mime_types={"text/plain", "text/html"},
                allowed_hosts=allowed_hosts,
                allow_private_hosts=allow_private_hosts,
            )
            if len(result.body) > max_bytes:
                raise SafetyError("robots response body exceeds the byte cap")
            lines = result.body.decode("utf-8", errors="replace").splitlines()
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(lines)
            self._robots[key] = (parser, len(result.body))
            return parser, len(result.body)
        except (NetworkError, SafetyError):
            if unavailable_policy == "allow":
                self._robots[key] = (None, 0)
                return None, 0
            raise SafetyError("robots policy is unavailable and fetch policy is deny") from None
