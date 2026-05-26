"""
analyzers/page_structure.py — URL, internal/external link structure checks.

Checks: URL length, URL format (hyphens, depth, case), internal link count,
external links, empty anchor text, nofollow usage.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse, urljoin
from .base import BaseAnalyzer, CategoryResult, Check, Status


class PageStructureAnalyzer(BaseAnalyzer):
    category     = "page_structure"
    display_name = "Page Structure"
    weight       = 0.20

    def analyze(self, page_data: dict) -> CategoryResult:
        soup       = page_data["soup"]
        url        = page_data["final_url"] or page_data["url"]
        checks: list[Check] = []

        parsed = urlparse(url)
        path   = parsed.path

        # ── 1. URL length ─────────────────────────────────────────────────
        url_len = len(url)
        if url_len <= 75:
            checks.append(Check(
                id="url_length", name="URL Length",
                status=Status.GOOD, value=f"{url_len} chars",
                description="URL length is optimal (≤ 75 characters).",
                points=10, max_points=10,
            ))
        elif url_len <= 115:
            checks.append(Check(
                id="url_length", name="URL Length",
                status=Status.WARNING, value=f"{url_len} chars",
                description="URL is slightly long (76–115 chars).",
                recommendation="Keep URLs concise — remove stop words and redundant path segments.",
                points=5, max_points=10,
            ))
        else:
            checks.append(Check(
                id="url_length", name="URL Length",
                status=Status.ERROR, value=f"{url_len} chars",
                description="URL is too long (> 115 chars).",
                recommendation="Shorten the URL. Long URLs are truncated in SERPs and harder to share.",
                points=0, max_points=10,
            ))

        # ── 2. URL uses hyphens (not underscores) ─────────────────────────
        if "_" in path:
            checks.append(Check(
                id="url_hyphens", name="URL Word Separators",
                status=Status.WARNING, value="Underscores found",
                description="URL uses underscores as word separators.",
                recommendation="Replace underscores with hyphens. Google treats hyphens as word separators.",
                points=3, max_points=8,
            ))
        else:
            checks.append(Check(
                id="url_hyphens", name="URL Word Separators",
                status=Status.GOOD, value="Hyphens used",
                description="URL uses hyphens as word separators — correct.",
                points=8, max_points=8,
            ))

        # ── 3. URL lowercase ──────────────────────────────────────────────
        if path != path.lower():
            checks.append(Check(
                id="url_case", name="URL Case",
                status=Status.WARNING, value="Contains uppercase letters",
                description="URL contains uppercase letters.",
                recommendation="Use all-lowercase URLs to avoid duplicate content issues.",
                points=3, max_points=7,
            ))
        else:
            checks.append(Check(
                id="url_case", name="URL Case",
                status=Status.GOOD, value="All lowercase",
                description="URL is all lowercase — good.",
                points=7, max_points=7,
            ))

        # ── 4. URL depth ──────────────────────────────────────────────────
        depth = len([p for p in path.split("/") if p])
        if depth <= 3:
            checks.append(Check(
                id="url_depth", name="URL Depth",
                status=Status.GOOD, value=f"{depth} level(s) deep",
                description="URL depth is shallow (≤ 3 levels) — good for crawlability.",
                points=8, max_points=8,
            ))
        elif depth <= 5:
            checks.append(Check(
                id="url_depth", name="URL Depth",
                status=Status.WARNING, value=f"{depth} levels deep",
                description="URL is moderately deep (4–5 levels).",
                recommendation="Consider flattening your URL structure for better crawlability.",
                points=4, max_points=8,
            ))
        else:
            checks.append(Check(
                id="url_depth", name="URL Depth",
                status=Status.ERROR, value=f"{depth} levels deep",
                description="URL is deeply nested (> 5 levels).",
                recommendation="Restructure to reduce nesting depth for better SEO and UX.",
                points=0, max_points=8,
            ))

        # ── 5. Analyse all links ──────────────────────────────────────────
        base_domain = f"{parsed.scheme}://{parsed.netloc}"
        all_links   = soup.find_all("a", href=True)

        internal_links = []
        external_links = []
        empty_anchor   = 0
        nofollow_ext   = 0

        for a in all_links:
            href = a["href"].strip()
            text = a.get_text(strip=True)

            # Skip anchors, mailto, tel, javascript
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            abs_href = urljoin(url, href)
            a_parsed = urlparse(abs_href)

            if a_parsed.netloc == parsed.netloc:
                internal_links.append(abs_href)
            else:
                external_links.append(abs_href)
                rel = a.get("rel", [])
                if isinstance(rel, list) and any(
                    r in ("nofollow", "noreferrer", "noopener") for r in rel
                ):
                    nofollow_ext += 1

            if not text:
                empty_anchor += 1

        # ── 5a. Internal links ────────────────────────────────────────────
        n_int = len(internal_links)
        if n_int >= 3:
            checks.append(Check(
                id="internal_links", name="Internal Links",
                status=Status.GOOD, value=f"{n_int} internal links",
                description="Page has sufficient internal links.",
                points=15, max_points=15,
            ))
        elif n_int >= 1:
            checks.append(Check(
                id="internal_links", name="Internal Links",
                status=Status.WARNING, value=f"{n_int} internal link(s)",
                description="Very few internal links found.",
                recommendation="Add more internal links to help search engines discover and rank other pages.",
                points=7, max_points=15,
            ))
        else:
            checks.append(Check(
                id="internal_links", name="Internal Links",
                status=Status.ERROR, value="No internal links",
                description="No internal links found on this page.",
                recommendation="Add internal links to related pages to improve site crawlability and UX.",
                points=0, max_points=15,
            ))

        # ── 5b. External link nofollow ────────────────────────────────────
        n_ext = len(external_links)
        if n_ext > 0:
            if nofollow_ext >= n_ext * 0.5:
                checks.append(Check(
                    id="ext_nofollow", name="External Link Attributes",
                    status=Status.GOOD,
                    value=f"{nofollow_ext}/{n_ext} external links have rel=nofollow",
                    description="Most external links use nofollow/noreferrer.",
                    points=10, max_points=10,
                ))
            else:
                checks.append(Check(
                    id="ext_nofollow", name="External Link Attributes",
                    status=Status.WARNING,
                    value=f"{n_ext - nofollow_ext}/{n_ext} external links missing rel attribute",
                    description="Several external links do not have rel=nofollow.",
                    recommendation="Add rel='nofollow noreferrer' to external links you don't want to pass authority to.",
                    points=4, max_points=10,
                ))
        else:
            checks.append(Check(
                id="ext_nofollow", name="External Link Attributes",
                status=Status.INFO, value="No external links",
                description="No external links found on this page.",
                points=10, max_points=10,
            ))

        # ── 5c. Empty anchor text ─────────────────────────────────────────
        if empty_anchor == 0:
            checks.append(Check(
                id="empty_anchors", name="Empty Anchor Text",
                status=Status.GOOD, value="None found",
                description="All links have descriptive anchor text.",
                points=7, max_points=7,
            ))
        else:
            checks.append(Check(
                id="empty_anchors", name="Empty Anchor Text",
                status=Status.WARNING, value=f"{empty_anchor} link(s) with no text",
                description=f"{empty_anchor} link(s) have empty anchor text.",
                recommendation="Add descriptive text to all links for better accessibility and SEO.",
                points=max(0, 7 - empty_anchor * 2), max_points=7,
            ))

        # ── 6. URL contains keyword signals (no query-only URLs) ──────────
        query = parsed.query
        if query and not path.strip("/"):
            checks.append(Check(
                id="url_query_only", name="URL Structure",
                status=Status.WARNING, value="Query-string only URL",
                description="URL consists entirely of query parameters (e.g. ?id=123).",
                recommendation="Use clean, descriptive URL paths instead of query-only URLs.",
                points=3, max_points=7,
            ))
        else:
            checks.append(Check(
                id="url_query_only", name="URL Structure",
                status=Status.GOOD, value="Clean URL path",
                description="URL uses a clean path structure.",
                points=7, max_points=7,
            ))

        score = self.calc_score(checks)
        return CategoryResult(
            category=self.category,
            display_name=self.display_name,
            score=score,
            checks=checks,
            weight=self.weight,
        )
