"""
analyzers/performance.py — Google PageSpeed Insights v5 integration.

Calls the PSI API for both MOBILE and DESKTOP strategies and extracts:
  • Lighthouse category scores: Performance, SEO, Accessibility, Best Practices
  • Core Web Vitals: LCP, CLS, FCP, TBT, Speed Index, TTI
  • CrUX real-user data (overall_category + key metrics)
  • Top opportunities / diagnostics from the Lighthouse audit map

Gracefully degrades if GOOGLE_PAGESPEED_API_KEY is not set — returns an
INFO check so the rest of the analysis still completes.

API reference: https://developers.google.com/speed/docs/insights/rest/v5/pagespeedapi/runpagespeed
"""
from __future__ import annotations

import logging

import httpx
from django.conf import settings

from .base import BaseAnalyzer, CategoryResult, Check, Status

logger = logging.getLogger(__name__)

PSI_ENDPOINT = "https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"

# Lighthouse audit IDs we surface as individual checks
CORE_VITALS = {
    "first-contentful-paint":       ("FCP",          "First Contentful Paint"),
    "largest-contentful-paint":     ("LCP",          "Largest Contentful Paint"),
    "total-blocking-time":          ("TBT",          "Total Blocking Time"),
    "cumulative-layout-shift":      ("CLS",          "Cumulative Layout Shift"),
    "speed-index":                  ("SI",           "Speed Index"),
    "interactive":                  ("TTI",          "Time to Interactive"),
    "server-response-time":         ("TTFB",         "Server Response Time (TTFB)"),
}

# Opportunity / diagnostic audits that carry actionable savings
OPPORTUNITY_AUDITS = [
    "render-blocking-resources",
    "unused-css-rules",
    "unused-javascript",
    "uses-optimized-images",
    "uses-webp-images",
    "uses-text-compression",
    "uses-responsive-images",
    "efficient-animated-content",
    "offscreen-images",
]


class PerformanceAnalyzer(BaseAnalyzer):
    category     = "performance"
    display_name = "Performance (PageSpeed)"
    weight       = 0.0   # advisory — does not affect weighted SEO score

    def analyze(self, page_data: dict) -> CategoryResult:
        checks: list[Check] = []
        url = page_data["final_url"] or page_data["url"]

        api_key = getattr(settings, "GOOGLE_PAGESPEED_API_KEY", "")
        if not api_key:
            checks.append(Check(
                id="psi_unavailable", name="PageSpeed Insights",
                status=Status.INFO,
                value="GOOGLE_PAGESPEED_API_KEY not configured",
                description=(
                    "Add GOOGLE_PAGESPEED_API_KEY to your .env to enable "
                    "real Lighthouse performance data."
                ),
                points=0, max_points=0,
            ))
            return _result(checks, 0)

        # Run both strategies; primary score comes from mobile (stricter)
        mobile_data  = _call_psi(url, api_key, strategy="mobile")
        desktop_data = _call_psi(url, api_key, strategy="desktop")

        if mobile_data is None and desktop_data is None:
            checks.append(Check(
                id="psi_error", name="PageSpeed Insights",
                status=Status.WARNING,
                value="API call failed",
                description="PageSpeed Insights could not analyse this URL.",
                recommendation="Check your API key quota and ensure the URL is publicly reachable.",
                points=0, max_points=0,
            ))
            return _result(checks, 0)

        primary = mobile_data or desktop_data

        # ── Lighthouse category scores ─────────────────────────────────────
        cats = (primary.get("lighthouseResult") or {}).get("categories") or {}
        perf_score = _lh_score(cats, "performance")
        seo_score  = _lh_score(cats, "seo")
        a11y_score = _lh_score(cats, "accessibility")
        bp_score   = _lh_score(cats, "best-practices")

        checks.append(_score_check(
            "lh_performance", "Lighthouse Performance Score",
            perf_score, thresholds=(90, 50),
            good_pts=30, max_pts=30,
            good_desc="Excellent Lighthouse performance score.",
            warn_desc="Performance score needs improvement.",
            fail_desc="Poor performance score — significant optimisation required.",
            recommendation="Audit Core Web Vitals and eliminate render-blocking resources.",
        ))

        if seo_score is not None:
            checks.append(_score_check(
                "lh_seo", "Lighthouse SEO Score",
                seo_score, thresholds=(90, 50),
                good_pts=15, max_pts=15,
                good_desc="Lighthouse SEO audit passed.",
                warn_desc="Some Lighthouse SEO audits need attention.",
                fail_desc="Multiple Lighthouse SEO audits failed.",
                recommendation="Review Lighthouse SEO audit details for actionable fixes.",
            ))

        if a11y_score is not None:
            checks.append(_score_check(
                "lh_accessibility", "Lighthouse Accessibility Score",
                a11y_score, thresholds=(90, 50),
                good_pts=10, max_pts=10,
                good_desc="Good accessibility score.",
                warn_desc="Some accessibility issues detected.",
                fail_desc="Significant accessibility problems found.",
                recommendation="Fix contrast ratios, ARIA labels, and keyboard navigation.",
            ))

        if bp_score is not None:
            checks.append(_score_check(
                "lh_best_practices", "Lighthouse Best Practices",
                bp_score, thresholds=(90, 50),
                good_pts=10, max_pts=10,
                good_desc="Follows modern web best practices.",
                warn_desc="Some best practice issues.",
                fail_desc="Multiple best practice failures.",
                recommendation="Check for deprecated APIs, mixed content, and JS errors.",
            ))

        # ── Desktop vs Mobile score delta ──────────────────────────────────
        if mobile_data and desktop_data:
            mob_p = _lh_score((mobile_data.get("lighthouseResult") or {}).get("categories") or {}, "performance")
            dsk_p = _lh_score((desktop_data.get("lighthouseResult") or {}).get("categories") or {}, "performance")
            if mob_p is not None and dsk_p is not None:
                delta = dsk_p - mob_p
                checks.append(Check(
                    id="mobile_desktop_gap", name="Mobile vs Desktop Score",
                    status=Status.GOOD if delta <= 20 else Status.WARNING,
                    value=f"Mobile {mob_p} / Desktop {dsk_p}",
                    description=f"Performance gap between desktop and mobile is {delta} points.",
                    recommendation=(
                        "" if delta <= 20
                        else "Optimise images, reduce JS payload, and enable lazy-loading for mobile."
                    ),
                    points=5 if delta <= 20 else 2, max_points=5,
                ))

        # ── Core Web Vitals ────────────────────────────────────────────────
        audits = (primary.get("lighthouseResult") or {}).get("audits") or {}
        for audit_id, (short, label) in CORE_VITALS.items():
            audit = audits.get(audit_id)
            if not audit:
                continue
            display_val = audit.get("displayValue", "")
            score_val   = audit.get("score")          # 0.0–1.0 or None

            if score_val is None:
                st = Status.INFO
            elif score_val >= 0.9:
                st = Status.GOOD
            elif score_val >= 0.5:
                st = Status.WARNING
            else:
                st = Status.ERROR

            checks.append(Check(
                id=f"cwv_{audit_id.replace('-', '_')}",
                name=f"{label} ({short})",
                status=st,
                value=display_val,
                description=audit.get("description", "")[:200],
                recommendation="" if st == Status.GOOD else _cwv_recommendation(audit_id),
                points=0, max_points=0,
            ))

        # ── CrUX real-user data ────────────────────────────────────────────
        loading = primary.get("loadingExperience") or {}
        crux_cat = loading.get("overall_category", "")
        if crux_cat:
            crux_status = {
                "FAST":   Status.GOOD,
                "AVERAGE": Status.WARNING,
                "SLOW":   Status.ERROR,
            }.get(crux_cat.upper(), Status.INFO)
            checks.append(Check(
                id="crux_overall", name="CrUX Real-User Experience",
                status=crux_status,
                value=crux_cat.title(),
                description=(
                    "Based on real Chrome user data (CrUX) — "
                    "reflects actual visitor experience, not lab simulation."
                ),
                recommendation=(
                    "" if crux_status == Status.GOOD
                    else "Improve Core Web Vitals to move from field data to FAST rating."
                ),
                points=0, max_points=0,
            ))

        # ── Top opportunities ──────────────────────────────────────────────
        for audit_id in OPPORTUNITY_AUDITS:
            audit = audits.get(audit_id)
            if not audit:
                continue
            score_val = audit.get("score")
            if score_val is None or score_val >= 0.9:
                continue   # passed — skip
            savings = audit.get("details", {}).get("overallSavingsMs")
            savings_str = (
                f" (~{round(savings / 1000, 1)}s savings)" if savings else ""
            )
            checks.append(Check(
                id=f"opp_{audit_id.replace('-', '_')}",
                name=audit.get("title", audit_id),
                status=Status.WARNING if (score_val or 0) >= 0.5 else Status.ERROR,
                value=audit.get("displayValue", "") + savings_str,
                description=audit.get("description", "")[:200],
                recommendation="",
                points=0, max_points=0,
            ))

        # Overall score = Lighthouse performance score (0-100)
        overall = perf_score if perf_score is not None else 0
        return _result(checks, overall)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _call_psi(url: str, api_key: str, strategy: str) -> dict | None:
    params = {
        "url":      url,
        "key":      api_key,
        "strategy": strategy,
        "category": ["performance", "seo", "accessibility", "best-practices"],
    }
    try:
        resp = httpx.get(PSI_ENDPOINT, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("PSI %s call failed for %s: %s", strategy, url, exc)
        return None


def _lh_score(categories: dict, key: str) -> int | None:
    cat = categories.get(key)
    if cat is None:
        return None
    score = cat.get("score")
    if score is None:
        return None
    return round(float(score) * 100)


def _score_check(
    cid: str, name: str, score: int | None,
    thresholds: tuple[int, int],
    good_pts: int, max_pts: int,
    good_desc: str, warn_desc: str, fail_desc: str,
    recommendation: str,
) -> Check:
    if score is None:
        return Check(id=cid, name=name, status=Status.INFO,
                     value="n/a", description="Score not available.",
                     points=0, max_points=max_pts)
    hi, lo = thresholds
    if score >= hi:
        return Check(id=cid, name=name, status=Status.GOOD,
                     value=f"{score}/100", description=good_desc,
                     points=good_pts, max_points=max_pts)
    if score >= lo:
        return Check(id=cid, name=name, status=Status.WARNING,
                     value=f"{score}/100", description=warn_desc,
                     recommendation=recommendation,
                     points=round(good_pts * score / 100), max_points=max_pts)
    return Check(id=cid, name=name, status=Status.ERROR,
                 value=f"{score}/100", description=fail_desc,
                 recommendation=recommendation,
                 points=0, max_points=max_pts)


def _cwv_recommendation(audit_id: str) -> str:
    return {
        "largest-contentful-paint":  "Optimise the largest image/text block: compress images, preload key resources, use a CDN.",
        "total-blocking-time":       "Reduce JS execution time: split bundles, defer non-critical scripts.",
        "cumulative-layout-shift":   "Add explicit width/height to images and ads; avoid inserting content above existing DOM.",
        "first-contentful-paint":    "Eliminate render-blocking resources and improve server response time.",
        "speed-index":               "Reduce the time for visual content to appear; optimise critical rendering path.",
        "interactive":               "Minimise main-thread work and reduce JS payload.",
        "server-response-time":      "Enable server-side caching, use a CDN, or upgrade hosting.",
    }.get(audit_id, "Review the Lighthouse audit for specific recommendations.")


def _result(checks: list[Check], score: int) -> CategoryResult:
    return CategoryResult(
        category=PerformanceAnalyzer.category,
        display_name=PerformanceAnalyzer.display_name,
        score=score,
        checks=checks,
        weight=0.0,
    )
