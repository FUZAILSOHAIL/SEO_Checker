"""
analyzers/server.py — Server configuration & HTTP-level checks.

Checks: HTTPS, HTTP status, response time, robots.txt, sitemap.xml,
HSTS header, Content-Type, X-Robots-Tag, redirect cleanliness.
"""
from __future__ import annotations
from urllib.parse import urlparse
import httpx
from .base import BaseAnalyzer, CategoryResult, Check, Status


class ServerAnalyzer(BaseAnalyzer):
    category     = "server"
    display_name = "Server Configuration"
    weight       = 0.20

    def analyze(self, page_data: dict) -> CategoryResult:
        url           = page_data["url"]
        final_url     = page_data["final_url"] or url
        status_code   = page_data["status_code"]
        response_time = page_data["response_time_ms"]
        headers       = page_data["headers"]
        redirect_count = page_data.get("redirect_count", 0)

        checks: list[Check] = []
        parsed      = urlparse(final_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"

        # ── 1. HTTPS ──────────────────────────────────────────────────────
        if parsed.scheme == "https":
            checks.append(Check(
                id="https", name="HTTPS",
                status=Status.GOOD, value="HTTPS enabled",
                description="Site is served over HTTPS — secure connection.",
                points=20, max_points=20,
            ))
        else:
            checks.append(Check(
                id="https", name="HTTPS",
                status=Status.ERROR, value="HTTP only",
                description="Site is served over plain HTTP (not HTTPS).",
                recommendation="Install an SSL/TLS certificate and redirect all HTTP traffic to HTTPS.",
                points=0, max_points=20,
            ))

        # ── 2. HTTP status code ───────────────────────────────────────────
        if status_code == 200:
            checks.append(Check(
                id="status_code", name="HTTP Status Code",
                status=Status.GOOD, value=str(status_code),
                description="Server returned 200 OK.",
                points=15, max_points=15,
            ))
        elif 300 <= status_code < 400:
            checks.append(Check(
                id="status_code", name="HTTP Status Code",
                status=Status.WARNING, value=str(status_code),
                description=f"Server returned a redirect ({status_code}).",
                recommendation="Ensure final destination returns 200. Too many redirects slow crawlers.",
                points=5, max_points=15,
            ))
        else:
            checks.append(Check(
                id="status_code", name="HTTP Status Code",
                status=Status.ERROR, value=str(status_code),
                description=f"Server returned error status {status_code}.",
                recommendation="Fix server errors. Crawlers cannot index pages that don't return 200.",
                points=0, max_points=15,
            ))

        # ── 3. Response time ──────────────────────────────────────────────
        rt = round(response_time)
        if response_time <= 500:
            checks.append(Check(
                id="response_time", name="Response Time",
                status=Status.GOOD, value=f"{rt} ms",
                description="Excellent server response time (≤ 500 ms).",
                points=15, max_points=15,
            ))
        elif response_time <= 1500:
            checks.append(Check(
                id="response_time", name="Response Time",
                status=Status.WARNING, value=f"{rt} ms",
                description="Acceptable response time (500–1500 ms).",
                recommendation="Optimize server response time: enable caching, use a CDN, or upgrade hosting.",
                points=7, max_points=15,
            ))
        else:
            checks.append(Check(
                id="response_time", name="Response Time",
                status=Status.ERROR, value=f"{rt} ms",
                description="Slow server response time (> 1500 ms).",
                recommendation="Response time is too slow. Enable caching, compress assets, use a CDN.",
                points=0, max_points=15,
            ))

        # ── 4. Redirect chain ─────────────────────────────────────────────
        if redirect_count == 0:
            checks.append(Check(
                id="redirects", name="Redirect Chain",
                status=Status.GOOD, value="No redirects",
                description="URL reaches its destination without any redirects.",
                points=10, max_points=10,
            ))
        elif redirect_count == 1:
            checks.append(Check(
                id="redirects", name="Redirect Chain",
                status=Status.WARNING, value=f"{redirect_count} redirect",
                description="One redirect in the chain.",
                recommendation="One redirect is acceptable but direct URLs are preferred.",
                points=5, max_points=10,
            ))
        else:
            checks.append(Check(
                id="redirects", name="Redirect Chain",
                status=Status.ERROR, value=f"{redirect_count} redirects",
                description="Multiple redirects detected in the chain.",
                recommendation="Fix redirect chains — each hop slows crawlers and wastes crawl budget.",
                points=0, max_points=10,
            ))

        # ── 5. robots.txt ─────────────────────────────────────────────────
        robots_ok, _ = _check_url_accessible(f"{base_origin}/robots.txt")
        if robots_ok:
            checks.append(Check(
                id="robots_txt", name="robots.txt",
                status=Status.GOOD, value="Found",
                description="robots.txt is accessible.",
                points=10, max_points=10,
            ))
        else:
            checks.append(Check(
                id="robots_txt", name="robots.txt",
                status=Status.WARNING, value="Not found",
                description="robots.txt file is missing or not accessible.",
                recommendation="Create a robots.txt at your domain root to guide search engine crawlers.",
                points=3, max_points=10,
            ))

        # ── 6. Sitemap ────────────────────────────────────────────────────
        sitemap_ok, _ = _check_url_accessible(f"{base_origin}/sitemap.xml")
        if sitemap_ok:
            checks.append(Check(
                id="sitemap", name="XML Sitemap",
                status=Status.GOOD, value="Found at /sitemap.xml",
                description="XML sitemap is accessible at /sitemap.xml.",
                points=10, max_points=10,
            ))
        else:
            # Try sitemap_index.xml
            sitemap_idx_ok, _ = _check_url_accessible(f"{base_origin}/sitemap_index.xml")
            if sitemap_idx_ok:
                checks.append(Check(
                    id="sitemap", name="XML Sitemap",
                    status=Status.GOOD, value="Found at /sitemap_index.xml",
                    description="Sitemap index found.",
                    points=10, max_points=10,
                ))
            else:
                checks.append(Check(
                    id="sitemap", name="XML Sitemap",
                    status=Status.WARNING, value="Not found",
                    description="No XML sitemap found at /sitemap.xml or /sitemap_index.xml.",
                    recommendation="Create and submit an XML sitemap to Google Search Console.",
                    points=3, max_points=10,
                ))

        # ── 7. HSTS header ────────────────────────────────────────────────
        hsts = headers.get("strict-transport-security", "")
        if hsts:
            checks.append(Check(
                id="hsts", name="HSTS Header",
                status=Status.GOOD, value=_trunc(hsts, 60),
                description="Strict-Transport-Security header is set.",
                points=5, max_points=5,
            ))
        else:
            checks.append(Check(
                id="hsts", name="HSTS Header",
                status=Status.WARNING, value="Not set",
                description="HSTS (Strict-Transport-Security) header is missing.",
                recommendation="Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains' to your server config.",
                points=0, max_points=5,
            ))

        # ── 8. X-Robots-Tag ──────────────────────────────────────────────
        x_robots = headers.get("x-robots-tag", "").lower()
        if "noindex" in x_robots:
            checks.append(Check(
                id="x_robots", name="X-Robots-Tag Header",
                status=Status.ERROR, value=x_robots,
                description="X-Robots-Tag header contains 'noindex' — page is blocked from indexing.",
                recommendation="Remove 'noindex' from X-Robots-Tag if you want this page indexed.",
                points=0, max_points=5,
            ))
        else:
            checks.append(Check(
                id="x_robots", name="X-Robots-Tag Header",
                status=Status.GOOD, value=x_robots or "Not set",
                description="X-Robots-Tag header does not block indexing.",
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


def _check_url_accessible(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        return resp.status_code == 200, str(resp.status_code)
    except Exception as exc:
        return False, str(exc)


def _trunc(text: str, n: int) -> str:
    return text[:n] + ("…" if len(text) > n else "")
