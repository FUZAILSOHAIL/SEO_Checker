"""
analyzers/external_signals.py — Structured data & social signal checks.

Checks: JSON-LD schema markup, schema type, Open Graph completeness,
Twitter Card completeness, favicon.
"""
from __future__ import annotations
import json
from .base import BaseAnalyzer, CategoryResult, Check, Status

KNOWN_SCHEMA_TYPES = {
    "article", "blogposting", "newsarticle", "product", "organization",
    "localbusiness", "person", "breadcrumblist", "webpage", "website",
    "faqpage", "howto", "recipe", "event", "review", "itemlist",
    "videoobject", "imageobject", "service",
}


class ExternalSignalsAnalyzer(BaseAnalyzer):
    category     = "external_signals"
    display_name = "External Signals"
    weight       = 0.10

    def analyze(self, page_data: dict) -> CategoryResult:
        soup = page_data["soup"]
        checks: list[Check] = []

        # ── 1. JSON-LD Schema Markup ──────────────────────────────────────
        json_ld_tags = soup.find_all("script", {"type": "application/ld+json"})
        valid_schemas = []
        schema_types  = []

        for tag in json_ld_tags:
            try:
                data = json.loads(tag.string or "{}")
                if isinstance(data, list):
                    valid_schemas.extend(data)
                elif isinstance(data, dict):
                    valid_schemas.append(data)
            except (json.JSONDecodeError, TypeError):
                pass

        for schema in valid_schemas:
            st = schema.get("@type", "")
            if isinstance(st, list):
                schema_types.extend([s.lower() for s in st])
            elif isinstance(st, str):
                schema_types.append(st.lower())

        if valid_schemas:
            checks.append(Check(
                id="json_ld", name="JSON-LD Schema Markup",
                status=Status.GOOD,
                value=f"{len(valid_schemas)} schema block(s)",
                description="JSON-LD structured data found.",
                points=20, max_points=20,
            ))
            # Check schema type quality
            known_found = [t for t in schema_types if t in KNOWN_SCHEMA_TYPES]
            if known_found:
                checks.append(Check(
                    id="schema_type", name="Schema Type",
                    status=Status.GOOD,
                    value=", ".join(set(known_found)),
                    description=f"Recognised schema type(s) found: {', '.join(set(known_found))}.",
                    points=15, max_points=15,
                ))
            else:
                type_display = ", ".join(set(schema_types)) if schema_types else "unknown"
                checks.append(Check(
                    id="schema_type", name="Schema Type",
                    status=Status.WARNING,
                    value=type_display[:60],
                    description="Schema markup present but type is not a common rich-result type.",
                    recommendation="Use recognised types like Product, Article, FAQPage, LocalBusiness for rich results.",
                    points=7, max_points=15,
                ))
        else:
            checks.append(Check(
                id="json_ld", name="JSON-LD Schema Markup",
                status=Status.ERROR, value="Not found",
                description="No JSON-LD structured data found.",
                recommendation=(
                    "Add JSON-LD schema markup to enable rich results in Google Search. "
                    "Start with the appropriate @type for your page (Article, Product, FAQPage, etc.)."
                ),
                points=0, max_points=20,
            ))
            checks.append(Check(
                id="schema_type", name="Schema Type",
                status=Status.ERROR, value="N/A",
                description="Cannot check — no JSON-LD markup found.",
                points=0, max_points=15,
            ))

        # ── 2. Open Graph completeness ────────────────────────────────────
        og_fields = {
            "og:title":       "OG Title",
            "og:description": "OG Description",
            "og:image":       "OG Image",
            "og:url":         "OG URL",
            "og:type":        "OG Type",
        }
        og_present = {}
        for prop in og_fields:
            tag = soup.find("meta", {"property": prop})
            og_present[prop] = bool(tag and tag.get("content", "").strip())

        og_count = sum(og_present.values())
        if og_count >= 4:
            checks.append(Check(
                id="og_completeness", name="Open Graph Tags",
                status=Status.GOOD, value=f"{og_count}/5 OG tags present",
                description="Open Graph tags are well implemented.",
                points=20, max_points=20,
            ))
        elif og_count >= 2:
            missing = [og_fields[p] for p, v in og_present.items() if not v]
            checks.append(Check(
                id="og_completeness", name="Open Graph Tags",
                status=Status.WARNING, value=f"{og_count}/5 OG tags present",
                description=f"Some Open Graph tags are missing: {', '.join(missing)}.",
                recommendation=f"Add the missing OG tags: {', '.join(missing)}.",
                points=10, max_points=20,
            ))
        else:
            checks.append(Check(
                id="og_completeness", name="Open Graph Tags",
                status=Status.ERROR, value=f"{og_count}/5 OG tags present",
                description="Most Open Graph tags are missing. Social shares will look plain.",
                recommendation="Add at least og:title, og:description, og:image, and og:url.",
                points=0, max_points=20,
            ))

        # ── 3. Twitter Card completeness ──────────────────────────────────
        import re
        tw_fields = {
            "twitter:card":        "Twitter Card Type",
            "twitter:title":       "Twitter Title",
            "twitter:description": "Twitter Description",
            "twitter:image":       "Twitter Image",
        }
        tw_present = {}
        for name_attr in tw_fields:
            tag = soup.find("meta", {"name": re.compile(rf"^{re.escape(name_attr)}$", re.I)})
            tw_present[name_attr] = bool(tag and tag.get("content", "").strip())

        tw_count = sum(tw_present.values())
        if tw_count >= 3:
            checks.append(Check(
                id="twitter_card", name="Twitter Card Tags",
                status=Status.GOOD, value=f"{tw_count}/4 Twitter tags present",
                description="Twitter Card tags are well implemented.",
                points=15, max_points=15,
            ))
        elif tw_count >= 1:
            checks.append(Check(
                id="twitter_card", name="Twitter Card Tags",
                status=Status.WARNING, value=f"{tw_count}/4 Twitter tags present",
                description="Twitter Card is partially implemented.",
                recommendation="Add twitter:card, twitter:title, twitter:description, and twitter:image.",
                points=7, max_points=15,
            ))
        else:
            checks.append(Check(
                id="twitter_card", name="Twitter Card Tags",
                status=Status.WARNING, value="Not implemented",
                description="No Twitter Card meta tags found.",
                recommendation="Add Twitter Card tags for richer shares on X/Twitter.",
                points=2, max_points=15,
            ))

        # ── 4. Favicon ────────────────────────────────────────────────────
        favicon = (
            soup.find("link", {"rel": re.compile(r"icon", re.I)})
            or soup.find("link", {"rel": re.compile(r"shortcut icon", re.I)})
        )
        if favicon and favicon.get("href", "").strip():
            checks.append(Check(
                id="favicon", name="Favicon",
                status=Status.GOOD, value=_trunc(favicon["href"], 60),
                description="Favicon link tag found.",
                points=10, max_points=10,
            ))
        else:
            checks.append(Check(
                id="favicon", name="Favicon",
                status=Status.WARNING, value="Not declared in HTML",
                description="No favicon link tag in HTML head.",
                recommendation="Add <link rel='icon' href='/favicon.ico'> for browser tabs and bookmarks.",
                points=3, max_points=10,
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
