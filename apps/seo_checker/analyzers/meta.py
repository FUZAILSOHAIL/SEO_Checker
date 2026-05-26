"""
analyzers/meta.py — Meta information checks.

Checks: title, meta description, robots directives, canonical, lang,
viewport, Open Graph tags, Twitter Card tags.
"""
from __future__ import annotations
import re
from .base import BaseAnalyzer, CategoryResult, Check, Status


class MetaAnalyzer(BaseAnalyzer):
    category     = "meta"
    display_name = "Meta Information"
    weight       = 0.25

    def analyze(self, page_data: dict) -> CategoryResult:
        soup = page_data["soup"]
        checks: list[Check] = []

        # ── 1. Title tag ──────────────────────────────────────────────────
        title_tag = soup.find("title")
        title_text = (title_tag.get_text(strip=True) if title_tag else "").strip()

        if title_text:
            checks.append(Check(
                id="title_present", name="Title Tag",
                status=Status.GOOD, value=_trunc(title_text, 60),
                description="Title tag is present.",
                points=15, max_points=15,
            ))
            length = len(title_text)
            if 50 <= length <= 65:
                checks.append(Check(
                    id="title_length", name="Title Length",
                    status=Status.GOOD, value=f"{length} chars",
                    description="Title length is optimal (50–65 chars).",
                    points=10, max_points=10,
                ))
            elif 40 <= length < 50 or 65 < length <= 75:
                checks.append(Check(
                    id="title_length", name="Title Length",
                    status=Status.WARNING, value=f"{length} chars",
                    description="Title length is slightly outside the 50–65 char sweet spot.",
                    recommendation="Adjust your title to 50–65 characters for best SERP display.",
                    points=5, max_points=10,
                ))
            else:
                checks.append(Check(
                    id="title_length", name="Title Length",
                    status=Status.ERROR, value=f"{length} chars",
                    description="Title is too short (< 40) or too long (> 75 chars).",
                    recommendation="Rewrite title to be 50–65 characters. Very long titles get truncated in SERPs.",
                    points=0, max_points=10,
                ))
        else:
            checks.append(Check(
                id="title_present", name="Title Tag",
                status=Status.ERROR, value="Missing",
                description="No <title> tag found on this page.",
                recommendation="Add a unique, descriptive title of 50–65 characters.",
                points=0, max_points=15,
            ))
            checks.append(Check(
                id="title_length", name="Title Length",
                status=Status.ERROR, value="N/A",
                description="Cannot check length — title tag is missing.",
                points=0, max_points=10,
            ))

        # ── 2. Meta description ───────────────────────────────────────────
        meta_desc_tag = soup.find("meta", {"name": re.compile(r"^description$", re.I)})
        desc_text = ""
        if meta_desc_tag:
            desc_text = meta_desc_tag.get("content", "").strip()

        if desc_text:
            checks.append(Check(
                id="meta_desc_present", name="Meta Description",
                status=Status.GOOD, value=_trunc(desc_text, 80),
                description="Meta description is present.",
                points=15, max_points=15,
            ))
            dl = len(desc_text)
            if 130 <= dl <= 165:
                checks.append(Check(
                    id="meta_desc_length", name="Meta Description Length",
                    status=Status.GOOD, value=f"{dl} chars",
                    description="Meta description length is optimal (130–165 chars).",
                    points=10, max_points=10,
                ))
            elif 100 <= dl < 130 or 165 < dl <= 185:
                checks.append(Check(
                    id="meta_desc_length", name="Meta Description Length",
                    status=Status.WARNING, value=f"{dl} chars",
                    description="Description is slightly outside the 130–165 char range.",
                    recommendation="Adjust to 130–165 characters to maximise SERP snippet use.",
                    points=5, max_points=10,
                ))
            else:
                checks.append(Check(
                    id="meta_desc_length", name="Meta Description Length",
                    status=Status.ERROR, value=f"{dl} chars",
                    description="Description is too short (< 100) or too long (> 185 chars).",
                    recommendation="Write a meta description of 130–165 characters that summarises the page.",
                    points=0, max_points=10,
                ))
        else:
            checks.append(Check(
                id="meta_desc_present", name="Meta Description",
                status=Status.ERROR, value="Missing",
                description="No meta description found.",
                recommendation="Add a unique meta description of 130–165 characters.",
                points=0, max_points=15,
            ))
            checks.append(Check(
                id="meta_desc_length", name="Meta Description Length",
                status=Status.ERROR, value="N/A",
                description="Cannot check length — description is missing.",
                points=0, max_points=10,
            ))

        # ── 3. Robots meta tag ────────────────────────────────────────────
        robots_tag = soup.find("meta", {"name": re.compile(r"^robots$", re.I)})
        if robots_tag:
            robots_content = robots_tag.get("content", "").lower()
            if "noindex" in robots_content:
                checks.append(Check(
                    id="robots_noindex", name="Robots: noindex",
                    status=Status.ERROR, value=robots_content,
                    description="This page is blocked from search engine indexing via noindex.",
                    recommendation="Remove 'noindex' unless you intentionally want this page excluded from search results.",
                    points=0, max_points=10,
                ))
            else:
                checks.append(Check(
                    id="robots_meta", name="Robots Meta Tag",
                    status=Status.GOOD, value=robots_content or "index, follow (default)",
                    description="No blocking directives (noindex) found.",
                    points=10, max_points=10,
                ))
        else:
            checks.append(Check(
                id="robots_meta", name="Robots Meta Tag",
                status=Status.GOOD, value="Not set (defaults to index, follow)",
                description="No robots meta tag — page uses default crawl/index behaviour.",
                points=10, max_points=10,
            ))

        # ── 4. Canonical URL ──────────────────────────────────────────────
        canonical = soup.find("link", {"rel": re.compile(r"canonical", re.I)})
        if canonical and canonical.get("href", "").strip():
            checks.append(Check(
                id="canonical", name="Canonical URL",
                status=Status.GOOD, value=_trunc(canonical["href"].strip(), 80),
                description="Canonical link tag is present.",
                points=10, max_points=10,
            ))
        else:
            checks.append(Check(
                id="canonical", name="Canonical URL",
                status=Status.WARNING, value="Missing",
                description="No canonical link tag found.",
                recommendation="Add <link rel='canonical' href='...'> to prevent duplicate content issues.",
                points=3, max_points=10,
            ))

        # ── 5. Language attribute ─────────────────────────────────────────
        html_tag = soup.find("html")
        lang = (html_tag.get("lang", "") if html_tag else "").strip()
        if lang:
            checks.append(Check(
                id="lang", name="Language Declaration",
                status=Status.GOOD, value=lang,
                description="Language is declared on the <html> element.",
                points=5, max_points=5,
            ))
        else:
            checks.append(Check(
                id="lang", name="Language Declaration",
                status=Status.WARNING, value="Missing",
                description="No lang attribute on <html> tag.",
                recommendation="Add lang attribute, e.g. <html lang='en'> to help search engines and screen readers.",
                points=0, max_points=5,
            ))

        # ── 6. Viewport meta ──────────────────────────────────────────────
        viewport = soup.find("meta", {"name": re.compile(r"^viewport$", re.I)})
        if viewport and viewport.get("content", "").strip():
            checks.append(Check(
                id="viewport", name="Viewport Meta Tag",
                status=Status.GOOD, value=_trunc(viewport["content"], 50),
                description="Viewport meta tag found — page is configured for mobile.",
                points=5, max_points=5,
            ))
        else:
            checks.append(Check(
                id="viewport", name="Viewport Meta Tag",
                status=Status.ERROR, value="Missing",
                description="No viewport meta tag found.",
                recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1'>.",
                points=0, max_points=5,
            ))

        # ── 7. Open Graph tags ────────────────────────────────────────────
        og_props = {
            "og:title":       ("og_title",       "OG Title",       5),
            "og:description": ("og_description", "OG Description", 5),
            "og:image":       ("og_image",       "OG Image",       5),
        }
        for prop, (cid, cname, pts) in og_props.items():
            tag = soup.find("meta", {"property": prop})
            if tag and tag.get("content", "").strip():
                checks.append(Check(
                    id=cid, name=cname,
                    status=Status.GOOD, value=_trunc(tag["content"], 60),
                    description=f"{prop} tag is present.",
                    points=pts, max_points=pts,
                ))
            else:
                checks.append(Check(
                    id=cid, name=cname,
                    status=Status.WARNING, value="Missing",
                    description=f"No {prop} tag found.",
                    recommendation=f"Add {prop} for richer social media previews.",
                    points=0, max_points=pts,
                ))

        # ── 8. Twitter Card ───────────────────────────────────────────────
        tw_card = soup.find("meta", {"name": re.compile(r"^twitter:card$", re.I)})
        if tw_card and tw_card.get("content", "").strip():
            checks.append(Check(
                id="twitter_card", name="Twitter Card",
                status=Status.GOOD, value=tw_card["content"],
                description="Twitter Card meta tag is present.",
                points=5, max_points=5,
            ))
        else:
            checks.append(Check(
                id="twitter_card", name="Twitter Card",
                status=Status.WARNING, value="Missing",
                description="No twitter:card meta tag found.",
                recommendation="Add twitter:card, twitter:title, twitter:description meta tags.",
                points=0, max_points=5,
            ))

        score = self.calc_score(checks)
        return CategoryResult(
            category=self.category,
            display_name=self.display_name,
            score=score,
            checks=checks,
            weight=self.weight,
        )


def _trunc(text: str, n: int) -> str:
    return text[:n] + ("…" if len(text) > n else "")
