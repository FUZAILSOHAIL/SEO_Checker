"""
analyzers/ai_insights.py — GPT-5.3 powered content quality & recommendation engine.

Runs AFTER all rule-based analyzers. It reads the actual page content and the
summary of existing failures, then produces:
  • An executive summary (plain-English overview)
  • Content quality score + specific content issues
  • Suggested title / meta description written for THIS page
  • Prioritized, context-aware action items

Gracefully degrades: if OPENAI_API_KEY is not configured or the API call fails,
it returns an INFO-level result so the rest of the check still completes.
"""
from __future__ import annotations

import json
import logging
import re

import openai
from django.conf import settings

from .base import BaseAnalyzer, CategoryResult, Check, Status

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior SEO consultant with deep expertise in on-page optimisation,
content strategy, and technical SEO. You analyze real webpages and give
specific, actionable advice.

You MUST return a single valid JSON object — no markdown, no prose, ONLY JSON.

Schema:
{
  "executive_summary": "<2–3 sentences summarising the page's overall SEO health, \
referencing actual content>",
  "content_quality_score": <integer 0–100>,
  "content_verdict": "<one of: excellent | good | thin | keyword_stuffed | off_topic>",
  "content_issues": ["<specific issue found in the actual page text>", ...],
  "suggested_title": "<SEO-optimised title for this specific page, \
or empty string if current title is already good>",
  "suggested_meta_description": "<SEO-optimised meta description for this page, \
or empty string if current one is already good>",
  "top_recommendations": [
    {
      "priority": <1–10, 1=highest>,
      "area": "<one of: Meta | Content | Structure | Technical | Schema>",
      "action": "<specific, concrete action referencing the actual page>",
      "expected_impact": "<High | Medium | Low>"
    }
  ]
}

Rules:
- Provide exactly 5–8 top_recommendations, ordered by priority (1 = most impactful).
- Be SPECIFIC. Reference the actual title, actual content topics, actual missing elements.
- Do NOT repeat rule-based issues already listed — add NEW insights only.
- If suggested_title / suggested_meta_description would be the same as the current,
  return empty string for those fields.
"""


def _build_user_message(page_data: dict, rule_based_failures: list[str]) -> str:
    soup = page_data["soup"]
    url  = page_data["final_url"] or page_data["url"]

    # Extract clean body text
    text_soup = soup.__copy__()
    for tag in text_soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    raw_text = re.sub(r"\s+", " ", text_soup.get_text(separator=" ", strip=True))
    page_text = raw_text[:4000]  # keep tokens reasonable

    title_tag  = soup.find("title")
    title      = title_tag.get_text(strip=True) if title_tag else "(missing)"

    meta_desc  = soup.find("meta", {"name": re.compile(r"^description$", re.I)})
    desc       = (meta_desc.get("content", "") if meta_desc else "").strip() or "(missing)"

    h1_tags    = soup.find_all("h1")
    h1_text    = " | ".join(h.get_text(strip=True) for h in h1_tags) or "(none)"

    h2_tags    = soup.find_all("h2")
    h2_preview = " | ".join(h.get_text(strip=True) for h in h2_tags[:6]) or "(none)"

    failures_block = (
        "\n".join(f"  - {f}" for f in rule_based_failures)
        if rule_based_failures
        else "  (none — page passed all rule-based checks)"
    )

    return f"""\
URL:               {url}
Current Title:     {title}
Current Meta Desc: {desc}
H1 Tags:           {h1_text}
H2 Tags (first 6): {h2_preview}

Page Text (first 4 000 chars):
{page_text}

Rule-Based Issues Already Detected (do NOT repeat these — add NEW insights only):
{failures_block}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Analyzer
# ──────────────────────────────────────────────────────────────────────────────

class AIInsightsAnalyzer(BaseAnalyzer):
    category     = "ai_insights"
    display_name = "AI Insights"
    weight       = 0.0   # does not contribute to the weighted overall score

    def analyze(
        self,
        page_data: dict,
        rule_based_failures: list[str] | None = None,
    ) -> tuple[CategoryResult, dict]:
        """
        Returns (CategoryResult, ai_extras) where ai_extras contains:
          executive_summary, suggested_title, suggested_meta_description,
          top_recommendations (list), content_quality_score, content_verdict.
        """
        checks: list[Check] = []
        ai_extras: dict = {}

        api_key = getattr(settings, "OPENAI_API_KEY", "")
        if not api_key:
            checks.append(Check(
                id="ai_unavailable", name="AI Analysis",
                status=Status.INFO,
                value="OPENAI_API_KEY not configured",
                description="Set OPENAI_API_KEY in your .env file to enable AI insights.",
                points=0, max_points=0,
            ))
            return _result(checks, ai_extras), ai_extras

        try:
            raw = _call_openai(
                api_key=api_key,
                user_message=_build_user_message(
                    page_data,
                    rule_based_failures or [],
                ),
            )
            ai_data = _parse_response(raw)
        except Exception as exc:
            logger.warning("AI insights call failed: %s", exc)
            checks.append(Check(
                id="ai_error", name="AI Analysis",
                status=Status.INFO,
                value="API call failed",
                description=f"AI analysis could not complete: {exc}",
                recommendation="Check your OpenAI API key and quota.",
                points=0, max_points=0,
            ))
            return _result(checks, ai_extras), ai_extras

        # ── Populate checks from AI response ──────────────────────────────
        score = ai_data.get("content_quality_score", 0)
        verdict = ai_data.get("content_verdict", "unknown")

        score_status = (
            Status.GOOD    if score >= 70
            else Status.WARNING if score >= 40
            else Status.ERROR
        )
        checks.append(Check(
            id="ai_content_score", name="AI Content Quality Score",
            status=score_status,
            value=f"{score}/100 — {verdict.replace('_', ' ').title()}",
            description=ai_data.get("executive_summary", ""),
            points=0, max_points=0,
        ))

        for issue in ai_data.get("content_issues", []):
            checks.append(Check(
                id=f"ai_issue_{_slug(issue)}", name="Content Issue",
                status=Status.WARNING,
                value="",
                description=issue,
                points=0, max_points=0,
            ))

        for rec in ai_data.get("top_recommendations", []):
            area   = rec.get("area", "")
            action = rec.get("action", "")
            impact = rec.get("expected_impact", "")
            prio   = rec.get("priority", 5)
            rec_status = Status.ERROR if prio <= 3 else (Status.WARNING if prio <= 6 else Status.INFO)
            checks.append(Check(
                id=f"ai_rec_{prio}_{_slug(area)}",
                name=f"[{area}] AI Recommendation",
                status=rec_status,
                value=f"Impact: {impact}",
                description=action,
                recommendation="",
                points=0, max_points=0,
            ))

        if ai_data.get("suggested_title"):
            checks.append(Check(
                id="ai_suggested_title", name="Suggested Title",
                status=Status.INFO,
                value=ai_data["suggested_title"],
                description="AI-generated SEO-optimised title for this page.",
                points=0, max_points=0,
            ))

        if ai_data.get("suggested_meta_description"):
            checks.append(Check(
                id="ai_suggested_desc", name="Suggested Meta Description",
                status=Status.INFO,
                value=ai_data["suggested_meta_description"],
                description="AI-generated meta description for this page.",
                points=0, max_points=0,
            ))

        ai_extras = {
            "executive_summary":           ai_data.get("executive_summary", ""),
            "content_quality_score":       score,
            "content_verdict":             verdict,
            "suggested_title":             ai_data.get("suggested_title", ""),
            "suggested_meta_description":  ai_data.get("suggested_meta_description", ""),
            "top_recommendations":         ai_data.get("top_recommendations", []),
        }

        return _result(checks, ai_extras), ai_extras


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _call_openai(api_key: str, user_message: str) -> str:
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-5.3",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.3,
        max_tokens=1200,
    )
    return response.choices[0].message.content or "{}"


def _parse_response(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Strip markdown fences if model ignored the JSON-only instruction
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(cleaned)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:30]


def _result(checks: list[Check], ai_extras: dict) -> CategoryResult:
    return CategoryResult(
        category=AIInsightsAnalyzer.category,
        display_name=AIInsightsAnalyzer.display_name,
        score=0,   # not scored
        checks=checks,
        weight=0.0,
    )
