#!/usr/bin/env python3
"""Safely inspect an official Parliament meeting page for public video-source hints.

This probe does not download media, access YouTube, use cookies, or change production.
It writes a redacted text report suitable for a GitHub Actions artifact.
"""
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
        a = dict(attrs)
        for key in ("src", "href", "data-src", "data-video", "poster"):
            val = a.get(key)
            if val:
                self.items.append((tag, key, html.unescape(val.strip())))

def main():
    page_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    req = urllib.request.Request(page_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(8_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        source = raw.decode(charset, errors="replace")
    parser = PageParser()
    parser.feed(source)
    found = set()
    lines = [
        "Official Parliament video-source probe",
        f"Page host: {urlparse(page_url).netloc}",
        f"HTTP page bytes read: {len(raw)}",
        "",
        "Candidate public URLs (no cookies or credentials used):",
    ]
    for tag, attr, value in parser.items:
        absolute = urljoin(page_url, value)
        low = absolute.lower()
        if any(x in low for x in ("youtube.com", "youtu.be", ".mp4", ".m3u8", ".mpd", "video", "stream", "media", "/api/")):
            if absolute.startswith(("http://", "https://")):
                found.add((tag, attr, absolute))
    # Look inside inline scripts and hydration JSON too, without executing JavaScript.
    for match in re.findall(r"""(?i)(?:https?:\\?/\\?/|/)[^"'\\s<>\\\\]{1,500}""", source):
        value = html.unescape(match).replace("\\/", "/").replace("&amp;", "&")
        absolute = urljoin(page_url, value)
        low = absolute.lower()
        if any(x in low for x in ("youtube.com", "youtu.be", ".mp4", ".m3u8", ".mpd", "video", "stream", "media", "/api/")):
            if absolute.startswith(("http://", "https://")):
                found.add(("inline-script", "url", absolute))
    if not found:
        lines.append("No obvious video/media/API URLs found in static HTML.")
        lines.append("Likely next step: inspect the page's public network requests / JavaScript app bundle.")
    else:
        for tag, attr, url in sorted(found):
            # URLs are public page references; do not print query values that could be tokens.
            p = urlparse(url)
            safe_url = p.scheme + "://" + p.netloc + p.path
            if p.query:
                safe_url += "?[query-redacted]"
            lines.append(f"- [{tag}.{attr}] {safe_url}")
    lines.extend(["", "Note: a URL match is only a lead, not proof that media is directly downloadable."])
    with open("official-video-source-probe.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
