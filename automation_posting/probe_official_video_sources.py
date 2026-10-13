#!/usr/bin/env python3
"""Read-only inspection of public HTML on an official Parliament meeting page."""
from __future__ import annotations
import html
import re
import sys
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

DEFAULT_URL = "https://digital.parliament.gov.np/baithak-detail/c97caf0c-e128-4dee-a3fe-b1dd3609ee80"
UA = "Mozilla/5.0 (compatible; ParliamentPulseSourceProbe/1.0)"

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("src", "href", "data-src", "data-video", "poster"):
            value = attrs.get(key)
            if value:
                self.items.append((tag, key, html.unescape(value.strip())))

def main():
    page_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    parsed_page = urlparse(page_url)
    if parsed_page.scheme != "https" or parsed_page.hostname != "digital.parliament.gov.np":
        raise SystemExit("Only https://digital.parliament.gov.np meeting pages are allowed.")
    request = urllib.request.Request(page_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read(8_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        source = raw.decode(charset, errors="replace")
    parser = PageParser()
    parser.feed(source)
    found = set()
    keywords = ("youtube.com", "youtu.be", ".mp4", ".m3u8", ".mpd", "video", "stream", "media", "/api/")
    for tag, attr, value in parser.items:
        absolute = urljoin(page_url, value)
        if absolute.startswith(("http://", "https://")) and any(k in absolute.lower() for k in keywords):
            found.add((tag, attr, absolute))
    # Search static script/hydration text only; never execute JavaScript.
    pattern = r"""(?:https?:\\?/\\?/|/)[^"'\s<>\\]{1,500}"""
    for match in re.findall(pattern, source, flags=re.IGNORECASE):
        value = html.unescape(match).replace("\\/", "/").replace("&amp;", "&")
        absolute = urljoin(page_url, value)
        if absolute.startswith(("http://", "https://")) and any(k in absolute.lower() for k in keywords):
            found.add(("inline-script", "url", absolute))
    lines = [
        "Official Parliament video-source probe",
        f"Page host: {parsed_page.netloc}",
        f"HTTP page bytes read: {len(raw)}",
        "",
        "Candidate public URLs (query strings redacted):",
    ]
    if not found:
        lines += [
            "No obvious video/media/API URLs found in static HTML.",
            "Next diagnostic step: inspect public JavaScript bundles or browser network requests.",
        ]
    for tag, attr, url in sorted(found):
        p = urlparse(url)
        safe_url = f"{p.scheme}://{p.netloc}{p.path}" + ("?[query-redacted]" if p.query else "")
        lines.append(f"- [{tag}.{attr}] {safe_url}")
    lines += ["", "A URL match is a lead, not proof the media is directly downloadable."]
    report = "\n".join(lines) + "\n"
    with open("official-video-source-probe.txt", "w", encoding="utf-8") as output:
        output.write(report)
    print(report, end="")

if __name__ == "__main__":
    main()
