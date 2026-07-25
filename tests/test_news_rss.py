"""Test RSS-parsing mot en fast fixture (ingen nettverk)."""

from __future__ import annotations

import feedparser

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Testfeed</title>
  <item>
    <title>Boligkrise rammer unge i Stavanger</title>
    <link>https://example.no/1</link>
    <pubDate>Wed, 23 Jul 2026 10:00:00 GMT</pubDate>
    <description>Studenter sliter paa leiemarkedet.</description>
  </item>
  <item>
    <title>Ny festival til byen</title>
    <link>https://example.no/2</link>
    <pubDate>Wed, 23 Jul 2026 09:00:00 GMT</pubDate>
    <description>Konsert og kultur.</description>
  </item>
</channel></rss>"""


def test_feedparser_reads_items():
    parsed = feedparser.parse(SAMPLE_RSS)
    assert len(parsed.entries) == 2
    assert parsed.entries[0].title.startswith("Boligkrise")
    assert parsed.entries[0].link == "https://example.no/1"
    assert parsed.entries[0].published_parsed is not None
