"""
analyzers/page_quality.py — Content & heading structure checks.

Checks: H1, heading hierarchy, word count, images alt text,
text/HTML ratio, paragraph structure.
"""
from __future__ import annotations
import re
from .base import BaseAnalyzer, CategoryResult, Check, Status


class PageQualityAnalyzer(BaseAnalyzer):
    category     = "page_quality"
    display_name = "Page Quality"
    weight       = 0.25

    def analyze(self, page_data: dict) -> CategoryResult:
        soup = page_data["soup"]
        checks: list[Check] = []

        body = soup.find("body") or soup

        # ── 1. H1 tag ─────────────────────────────────────────────────────
        h1_tags = body.find_all("h1")
        if h1_tags:
            h1_text = h1_tags[0].get_text(strip=True)
            checks.append(Check(
                id="h1_present", name="H1 Heading",
                status=Status.GOOD, value=_trunc(h1_text, 60),
                description="H1 heading is present.",
                points=15, max_points=15,
            ))
            if len(h1_tags) == 1:
                checks.append(Check(
                    id="h1_count", name="Single H1",
                    status=Status.GOOD, value="1 H1 tag",
                    description="Exactly one H1 tag found — ideal for SEO.",
                    points=10, max_points=10,
                ))
            else:
                checks.append(Check(
                    id="h1_count", name="Single H1",
                    status=Status.WARNING, value=f"{len(h1_tags)} H1 tags",
                    description="Multiple H1 tags found. Each page should have exactly one H1.",
                    recommendation="Keep only one H1 tag per page. Use H2–H6 for subheadings.",
                    points=3, max_points=10,
                ))
        else:
            checks.append(Check(
                id="h1_present", name="H1 Heading",
                status=Status.ERROR, value="Missing",
                description="No H1 heading found on this page.",
                recommendation="Add an H1 that includes your primary keyword and describes the page topic.",
                points=0, max_points=15,
            ))
            checks.append(Check(
                id="h1_count", name="Single H1",
                status=Status.ERROR, value="0 H1 tags",
                description="Cannot check — H1 is missing.",
                points=0, max_points=10,
            ))

        # ── 2. H2 tags ────────────────────────────────────────────────────
        h2_tags = body.find_all("h2")
        if h2_tags:
            checks.append(Check(
                id="h2_present", name="H2 Subheadings",
                status=Status.GOOD, value=f"{len(h2_tags)} H2 tags",
                description="H2 subheadings are present — good for content structure.",
                points=8, max_points=8,
            ))
        else:
            checks.append(Check(
                id="h2_present", name="H2 Subheadings",
                status=Status.WARNING, value="None found",
                description="No H2 subheadings found.",
                recommendation="Add H2 tags to structure content and help search engines understand sections.",
                points=2, max_points=8,
            ))

        # ── 3. Word count ─────────────────────────────────────────────────
        # Strip scripts, styles, nav, footer for cleaner word count
        text_soup = soup.__copy__()
        for tag in text_soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        raw_text  = text_soup.get_text(separator=" ", strip=True)
        word_count = len(re.findall(r"\b\w+\b", raw_text))

        if word_count >= 600:
            checks.append(Check(
                id="word_count", name="Word Count",
                status=Status.GOOD, value=f"{word_count} words",
                description="Page has substantial content (≥ 600 words).",
                points=15, max_points=15,
            ))
        elif word_count >= 300:
            checks.append(Check(
                id="word_count", name="Word Count",
                status=Status.WARNING, value=f"{word_count} words",
                description="Page has moderate content (300–599 words).",
                recommendation="Aim for 600+ words to compete for informational queries.",
                points=8, max_points=15,
            ))
        else:
            checks.append(Check(
                id="word_count", name="Word Count",
                status=Status.ERROR, value=f"{word_count} words",
                description="Page has very little text content (< 300 words).",
                recommendation="Add more substantive content — aim for at least 600 words.",
                points=0, max_points=15,
            ))

        # ── 4. Images with alt text ───────────────────────────────────────
        images = body.find_all("img")
        if images:
            without_alt = [
                img for img in images
                if not img.get("alt", "").strip()
            ]
            pct_ok = round(((len(images) - len(without_alt)) / len(images)) * 100)
            if len(without_alt) == 0:
                checks.append(Check(
                    id="img_alt", name="Image Alt Attributes",
                    status=Status.GOOD, value=f"All {len(images)} images have alt text",
                    description="All images have descriptive alt attributes — great for accessibility and SEO.",
                    points=12, max_points=12,
                ))
            elif pct_ok >= 75:
                checks.append(Check(
                    id="img_alt", name="Image Alt Attributes",
                    status=Status.WARNING,
                    value=f"{len(without_alt)} of {len(images)} images missing alt text",
                    description=f"{len(without_alt)} image(s) are missing alt attributes.",
                    recommendation="Add descriptive alt text to every image for better accessibility and image SEO.",
                    points=6, max_points=12,
                ))
            else:
                checks.append(Check(
                    id="img_alt", name="Image Alt Attributes",
                    status=Status.ERROR,
                    value=f"{len(without_alt)} of {len(images)} images missing alt text",
                    description="More than 25% of images are missing alt attributes.",
                    recommendation="Add descriptive alt text to every image.",
                    points=0, max_points=12,
                ))
        else:
            checks.append(Check(
                id="img_alt", name="Image Alt Attributes",
                status=Status.INFO, value="No images found",
                description="No images detected on this page.",
                points=12, max_points=12,  # Don't penalise pages with no images
            ))

        # ── 5. Text/HTML ratio ────────────────────────────────────────────
        html_str  = str(soup)
        html_size = len(html_str)
        text_size = len(raw_text)
        ratio     = round((text_size / html_size) * 100, 1) if html_size > 0 else 0

        if ratio >= 15:
            checks.append(Check(
                id="text_ratio", name="Text/HTML Ratio",
                status=Status.GOOD, value=f"{ratio}%",
                description="Good text-to-HTML ratio (≥ 15%).",
                points=10, max_points=10,
            ))
        elif ratio >= 8:
            checks.append(Check(
                id="text_ratio", name="Text/HTML Ratio",
                status=Status.WARNING, value=f"{ratio}%",
                description="Low text-to-HTML ratio (8–14%).",
                recommendation="Reduce inline CSS/JS and increase body text to improve this ratio.",
                points=4, max_points=10,
            ))
        else:
            checks.append(Check(
                id="text_ratio", name="Text/HTML Ratio",
                status=Status.ERROR, value=f"{ratio}%",
                description="Very low text-to-HTML ratio (< 8%). Too much code relative to content.",
                recommendation="Move CSS to external stylesheets, minify HTML, and add more body text.",
                points=0, max_points=10,
            ))

        # ── 6. Paragraph count ────────────────────────────────────────────
        paragraphs = body.find_all("p")
        if len(paragraphs) >= 4:
            checks.append(Check(
                id="paragraphs", name="Paragraph Structure",
                status=Status.GOOD, value=f"{len(paragraphs)} <p> tags",
                description="Content is well-structured with multiple paragraphs.",
                points=5, max_points=5,
            ))
        elif len(paragraphs) >= 1:
            checks.append(Check(
                id="paragraphs", name="Paragraph Structure",
                status=Status.WARNING, value=f"{len(paragraphs)} <p> tags",
                description="Few paragraph tags found.",
                recommendation="Break content into well-defined paragraphs using <p> tags.",
                points=2, max_points=5,
            ))
        else:
            checks.append(Check(
                id="paragraphs", name="Paragraph Structure",
                status=Status.ERROR, value="No <p> tags",
                description="No <p> paragraph tags found. Content may not be properly structured.",
                recommendation="Use <p> tags to wrap body text for better readability and SEO.",
                points=0, max_points=5,
            ))

        # ── 7. Heading hierarchy ──────────────────────────────────────────
        headings = [(int(t.name[1]), t) for t in body.find_all(re.compile(r"^h[1-6]$"))]
        if len(headings) >= 2:
            skip_found = False
            prev_level = 0
            for level, _ in headings:
                if prev_level > 0 and level > prev_level + 1:
                    skip_found = True
                    break
                prev_level = level
            if not skip_found:
                checks.append(Check(
                    id="heading_hierarchy", name="Heading Hierarchy",
                    status=Status.GOOD, value=f"{len(headings)} headings, proper nesting",
                    description="Heading levels are nested correctly (no skipped levels).",
                    points=5, max_points=5,
                ))
            else:
                checks.append(Check(
                    id="heading_hierarchy", name="Heading Hierarchy",
                    status=Status.WARNING, value="Skipped heading levels detected",
                    description="Heading levels skip (e.g. H1 → H3 without H2).",
                    recommendation="Ensure headings follow a logical order: H1 → H2 → H3.",
                    points=2, max_points=5,
                ))
        else:
            checks.append(Check(
                id="heading_hierarchy", name="Heading Hierarchy",
                status=Status.INFO, value="< 2 headings",
                description="Not enough headings to evaluate hierarchy.",
                points=5, max_points=5,
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
