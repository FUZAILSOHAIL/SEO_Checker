"""
seo_checker/tasks.py — Celery task that orchestrates the full SEO analysis.
"""
from __future__ import annotations
import ipaddress
import socket
import time
import traceback
from dataclasses import asdict
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

from .models import CheckCategory, CheckStatus, SeoCheck
from .analyzers.meta             import MetaAnalyzer
from .analyzers.page_quality     import PageQualityAnalyzer
from .analyzers.page_structure   import PageStructureAnalyzer
from .analyzers.server           import ServerAnalyzer
from .analyzers.external_signals import ExternalSignalsAnalyzer
from .analyzers.performance      import PerformanceAnalyzer
from .analyzers.ai_insights      import AIInsightsAnalyzer

logger = get_task_logger(__name__)

# Category weights for the overall score (must sum to 1.0)
CATEGORY_WEIGHTS = {
    "meta":             0.25,
    "page_quality":     0.25,
    "page_structure":   0.20,
    "server":           0.20,
    "external_signals": 0.10,
}

FETCH_TIMEOUT   = 20   # seconds
FETCH_MAX_SIZE  = 5 * 1024 * 1024   # 5 MB — prevent huge pages from stalling workers

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WebBoosterBot/1.0; +https://webbooster.app)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ──────────────────────────────────────────────────────────────────────────────
# Security — SSRF prevention
# ──────────────────────────────────────────────────────────────────────────────

def _is_safe_url(url: str) -> bool:
    """
    Reject requests to private/loopback addresses to prevent SSRF.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        ip_str = socket.gethostbyname(hostname)
        addr   = ipaddress.ip_address(ip_str)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
        ):
            return False
    except (socket.gaierror, ValueError):
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Page fetcher
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_page(url: str) -> dict:
    """
    Fetch a URL and return a page_data dict consumed by all analyzers.

    Security: follows redirects manually so every hop is SSRF-validated.
    """
    start        = time.monotonic()
    current_url  = url
    redirect_count = 0
    MAX_REDIRECTS  = 10

    with httpx.Client(
        headers=HEADERS,
        follow_redirects=False,   # we handle redirects manually for SSRF safety
        timeout=FETCH_TIMEOUT,
    ) as client:
        while redirect_count <= MAX_REDIRECTS:
            response = client.get(current_url)

            if response.is_redirect:
                next_url = str(response.headers.get("location", ""))
                # Resolve relative redirects
                if next_url.startswith("/"):
                    from urllib.parse import urlunparse, urlparse as _up
                    p = _up(current_url)
                    next_url = urlunparse((p.scheme, p.netloc, next_url, "", "", ""))
                # SSRF-check every redirect target
                if not _is_safe_url(next_url):
                    raise ValueError(f"Redirect to blocked address: {next_url}")
                current_url = next_url
                redirect_count += 1
                continue
            break   # non-redirect response

    elapsed_ms    = (time.monotonic() - start) * 1000
    final_url     = current_url
    headers_lower = {k.lower(): v for k, v in response.headers.items()}
    content_type  = headers_lower.get("content-type", "")

    # Only parse HTML pages
    raw_html = ""
    if "text/html" in content_type:
        raw_html = response.text[:FETCH_MAX_SIZE]

    soup = BeautifulSoup(raw_html, "lxml")

    title_tag  = soup.find("title")
    page_title = title_tag.get_text(strip=True) if title_tag else ""

    return {
        "url":            url,
        "final_url":      final_url,
        "status_code":    response.status_code,
        "response_time_ms": elapsed_ms,
        "redirect_count": redirect_count,
        "headers":        headers_lower,
        "html":           raw_html,
        "soup":           soup,
        "page_title":     page_title,
        "is_https":       final_url.startswith("https://"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main Celery task
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=0,          # Don't retry — return a failed result instead
    queue="seo_checks",
    name="seo_checker.run_seo_check",
)
def run_seo_check(self, check_id: str) -> dict:
    """
    Runs the complete 5-category SEO analysis for a given SeoCheck.

    Steps:
      1. Mark check as running.
      2. SSRF-validate and fetch the URL.
      3. Run all 5 rule-based analyzers against the parsed page data.
      4. Compute weighted overall score.
      5. Run GPT-4o AI insights analyzer (passes rule failures as context).
      6. Persist CheckCategory rows + AI fields.
      7. Mark check as complete.
    """
    check = SeoCheck.objects.get(id=check_id)
    check.status         = CheckStatus.RUNNING
    check.celery_task_id = self.request.id or ""
    check.save(update_fields=["status", "celery_task_id"])

    try:
        # ── SSRF check ────────────────────────────────────────────────────
        if not _is_safe_url(check.url):
            raise ValueError(f"URL '{check.url}' is not allowed (private/invalid address).")

        # ── Fetch page ────────────────────────────────────────────────────
        page_data = _fetch_page(check.url)

        # ── Run rule-based analyzers ──────────────────────────────────────
        rule_analyzers = [
            MetaAnalyzer(),
            PageQualityAnalyzer(),
            PageStructureAnalyzer(),
            ServerAnalyzer(),
            ExternalSignalsAnalyzer(),
            PerformanceAnalyzer(),   # PageSpeed Insights (advisory, weight=0)
        ]
        category_rows  = []
        weighted_sum   = 0.0
        rule_failures  = []   # collected for AI context

        for analyzer in rule_analyzers:
            result = analyzer.analyze(page_data)
            weight = CATEGORY_WEIGHTS.get(result.category, 0.2)
            weighted_sum += result.score * weight

            # Collect failures for AI prompt
            for c in result.checks:
                if c.status in ("error", "warning") and c.description:
                    rule_failures.append(f"[{result.display_name}] {c.name}: {c.description}")

            category_rows.append(CheckCategory(
                seo_check    = check,
                category     = result.category,
                display_name = result.display_name,
                score        = result.score,
                checks_data  = [asdict(c) for c in result.checks],
            ))
            logger.info(
                "Analyzer %s → score %d (weight %.2f)",
                result.category, result.score, weight
            )

        # ── AI insights (GPT-4o) ──────────────────────────────────────────
        ai_result, ai_extras = AIInsightsAnalyzer().analyze(
            page_data,
            rule_based_failures=rule_failures,
        )
        category_rows.append(CheckCategory(
            seo_check    = check,
            category     = ai_result.category,
            display_name = ai_result.display_name,
            score        = 0,
            checks_data  = [asdict(c) for c in ai_result.checks],
        ))
        logger.info("AI insights complete — %d checks", len(ai_result.checks))

        CheckCategory.objects.bulk_create(category_rows)

        overall = round(weighted_sum)
        check.overall_score = overall
        check.page_title    = page_data["page_title"]
        check.final_url     = page_data["final_url"]
        check.ai_summary    = ai_extras.get("executive_summary", "")
        check.ai_suggestions = {
            k: v for k, v in ai_extras.items() if k != "executive_summary"
        }
        check.status        = CheckStatus.COMPLETE
        check.completed_at  = timezone.now()
        check.save(update_fields=[
            "overall_score", "page_title", "final_url",
            "ai_summary", "ai_suggestions",
            "status", "completed_at",
        ])

        logger.info(
            "SEO check %s complete — %s — overall score: %d",
            check_id, check.url, overall,
        )
        return {"check_id": check_id, "overall_score": overall}

    except Exception as exc:
        check.status        = CheckStatus.FAILED
        check.error_message = str(exc)
        check.completed_at  = timezone.now()
        check.save(update_fields=["status", "error_message", "completed_at"])
        logger.error("SEO check %s failed: %s\n%s", check_id, exc, traceback.format_exc())
        return {"check_id": check_id, "error": str(exc)}
