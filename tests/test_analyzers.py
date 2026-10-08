import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.test import override_settings

from apps.seo_checker.analyzers.ai_insights import AIInsightsAnalyzer, _parse_response
from apps.seo_checker.analyzers.base import Status
from apps.seo_checker.analyzers.external_signals import ExternalSignalsAnalyzer
from apps.seo_checker.analyzers.meta import MetaAnalyzer
from apps.seo_checker.analyzers.page_quality import PageQualityAnalyzer
from apps.seo_checker.analyzers.page_structure import PageStructureAnalyzer
from apps.seo_checker.analyzers.performance import PSI_ENDPOINT, PerformanceAnalyzer
from apps.seo_checker.analyzers.server import ServerAnalyzer
from tests.helpers import checks_by_id, make_page_data

pytestmark = pytest.mark.django_db


def _meta_html(title: str, description: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <title>{title}</title>
  <meta name="description" content="{description}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="canonical" href="https://example.com/running-shoes">
  <meta property="og:title" content="Running shoes">
  <meta property="og:description" content="Shop running shoes">
  <meta property="og:image" content="https://example.com/og.png">
  <meta name="twitter:card" content="summary_large_image">
</head>
<body></body>
</html>
"""


def test_meta_analyzer_scores_a_complete_head():
    page = make_page_data(_meta_html("T" * 55, "D" * 150))
    result = MetaAnalyzer().analyze(page)
    found = checks_by_id(result)

    assert result.category == "meta"
    assert result.score == 100
    assert found["title_present"].status == Status.GOOD
    assert found["title_length"].status == Status.GOOD
    assert found["meta_desc_present"].status == Status.GOOD
    assert found["canonical"].status == Status.GOOD
    assert found["viewport"].status == Status.GOOD


def test_meta_analyzer_flags_a_missing_title_and_description():
    page = make_page_data("<!DOCTYPE html><html><head></head><body></body></html>")
    result = MetaAnalyzer().analyze(page)
    found = checks_by_id(result)

    assert found["title_present"].status == Status.ERROR
    assert found["meta_desc_present"].status == Status.ERROR
    assert found["viewport"].status == Status.ERROR
    assert result.score == 13


def test_page_quality_analyzer_scores_substantial_content():
    words = " ".join(["content"] * 650)
    html = f"""<!DOCTYPE html><html><body>
      <h1>Running shoes for daily training</h1>
      <h2>Fit and cushioning</h2>
      <p>{words}</p>
      <p>Second paragraph about training plans.</p>
      <p>Third paragraph about durability.</p>
      <p>Fourth paragraph about sizing.</p>
      <img src="/shoe.jpg" alt="Blue running shoe on a track">
    </body></html>"""
    result = PageQualityAnalyzer().analyze(make_page_data(html))
    found = checks_by_id(result)

    assert result.score == 100
    assert found["h1_present"].status == Status.GOOD
    assert found["h1_count"].status == Status.GOOD
    assert found["word_count"].status == Status.GOOD
    assert found["img_alt"].status == Status.GOOD
    assert found["text_ratio"].status == Status.GOOD


def test_page_quality_analyzer_flags_a_thin_page():
    result = PageQualityAnalyzer().analyze(
        make_page_data("<!DOCTYPE html><html><body><p>Hi</p></body></html>")
    )
    found = checks_by_id(result)

    assert found["h1_present"].status == Status.ERROR
    assert found["word_count"].status == Status.ERROR
    assert result.score < 50


def test_page_structure_analyzer_scores_a_clean_url_and_links():
    html = """<!DOCTYPE html><html><body>
      <a href="/guides">Guides</a>
      <a href="/sizing">Sizing</a>
      <a href="https://example.com/about">About</a>
      <a href="https://other.example/ref" rel="nofollow">Reference</a>
    </body></html>"""
    result = PageStructureAnalyzer().analyze(make_page_data(html))
    found = checks_by_id(result)

    assert result.score == 100
    assert found["url_length"].status == Status.GOOD
    assert found["url_hyphens"].status == Status.GOOD
    assert found["internal_links"].status == Status.GOOD
    assert found["empty_anchors"].status == Status.GOOD
    assert found["ext_nofollow"].status == Status.GOOD


def test_page_structure_analyzer_flags_ugly_urls_and_missing_links():
    page = make_page_data(
        "<!DOCTYPE html><html><body></body></html>",
        url="https://example.com/Running_Shoes",
        final_url="https://example.com/Running_Shoes",
    )
    found = checks_by_id(PageStructureAnalyzer().analyze(page))

    assert found["url_hyphens"].status == Status.WARNING
    assert found["url_case"].status == Status.WARNING
    assert found["internal_links"].status == Status.ERROR


def test_external_signals_analyzer_scores_schema_and_social_tags():
    html = """<!DOCTYPE html><html><head>
      <script type="application/ld+json">
        {"@context": "https://schema.org", "@type": "Article", "headline": "Shoes"}
      </script>
      <meta property="og:title" content="Shoes">
      <meta property="og:description" content="Buy shoes">
      <meta property="og:image" content="https://example.com/og.png">
      <meta property="og:url" content="https://example.com/running-shoes">
      <meta property="og:type" content="article">
      <meta name="twitter:card" content="summary">
      <meta name="twitter:title" content="Shoes">
      <meta name="twitter:description" content="Buy shoes">
      <meta name="twitter:image" content="https://example.com/og.png">
      <link rel="icon" href="/favicon.ico">
    </head><body></body></html>"""
    result = ExternalSignalsAnalyzer().analyze(make_page_data(html))
    found = checks_by_id(result)

    assert result.score == 100
    assert found["json_ld"].status == Status.GOOD
    assert found["schema_type"].status == Status.GOOD
    assert found["og_completeness"].status == Status.GOOD
    assert found["favicon"].status == Status.GOOD


def test_external_signals_analyzer_flags_missing_schema():
    result = ExternalSignalsAnalyzer().analyze(
        make_page_data("<!DOCTYPE html><html><head></head><body></body></html>")
    )
    found = checks_by_id(result)
    assert found["json_ld"].status == Status.ERROR
    assert found["schema_type"].status == Status.ERROR


def _http_response(status_code: int) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    return response


def test_server_analyzer_scores_a_healthy_https_response():
    page = make_page_data("<!DOCTYPE html><html></html>")
    with patch("apps.seo_checker.analyzers.server.httpx.get") as mocked:
        mocked.return_value = _http_response(200)
        result = ServerAnalyzer().analyze(page)

    found = checks_by_id(result)
    called = [call.args[0] for call in mocked.call_args_list]
    assert called == [
        "https://example.com/robots.txt",
        "https://example.com/sitemap.xml",
    ]
    assert result.score == 100
    assert found["https"].status == Status.GOOD
    assert found["status_code"].status == Status.GOOD
    assert found["robots_txt"].status == Status.GOOD
    assert found["sitemap"].status == Status.GOOD
    assert found["hsts"].status == Status.GOOD


def test_server_analyzer_flags_http_errors_and_missing_crawl_files():
    page = make_page_data(
        "<!DOCTYPE html><html></html>",
        url="http://example.com",
        final_url="http://example.com",
        status_code=500,
        response_time_ms=2400,
        redirect_count=3,
        headers={"content-type": "text/html"},
        is_https=False,
    )
    with patch("apps.seo_checker.analyzers.server.httpx.get") as mocked:
        mocked.side_effect = [
            _http_response(404),
            _http_response(404),
            _http_response(404),
        ]
        result = ServerAnalyzer().analyze(page)

    found = checks_by_id(result)
    assert found["https"].status == Status.ERROR
    assert found["status_code"].status == Status.ERROR
    assert found["response_time"].status == Status.ERROR
    assert found["redirects"].status == Status.ERROR
    assert found["robots_txt"].status == Status.WARNING
    assert found["sitemap"].status == Status.WARNING
    assert found["hsts"].status == Status.WARNING
    assert mocked.call_count == 3


def _psi_payload(performance: float) -> dict:
    return {
        "lighthouseResult": {
            "categories": {
                "performance": {"score": performance},
                "seo": {"score": 0.95},
                "accessibility": {"score": 0.91},
                "best-practices": {"score": 0.93},
            },
            "audits": {
                "largest-contentful-paint": {
                    "displayValue": "1.8 s",
                    "score": 0.92,
                    "description": "Largest Contentful Paint marks the paint time.",
                }
            },
        },
        "loadingExperience": {"overall_category": "FAST"},
    }


def _psi_response(performance: float) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = _psi_payload(performance)
    return response


def test_performance_analyzer_skips_pagespeed_without_a_key():
    with patch("apps.seo_checker.analyzers.performance.httpx.get") as mocked:
        result = PerformanceAnalyzer().analyze(make_page_data("<html></html>"))

    mocked.assert_not_called()
    assert result.score == 0
    assert checks_by_id(result)["psi_unavailable"].status == Status.INFO


@override_settings(GOOGLE_PAGESPEED_API_KEY="test-pagespeed-key")
def test_performance_analyzer_reads_mocked_lighthouse_scores():
    with patch("apps.seo_checker.analyzers.performance.httpx.get") as mocked:
        mocked.return_value = _psi_response(0.91)
        result = PerformanceAnalyzer().analyze(make_page_data("<html></html>"))

    assert mocked.call_count == 2
    strategies = set()
    for call in mocked.call_args_list:
        assert call.args[0] == PSI_ENDPOINT
        assert call.kwargs["params"]["key"] == "test-pagespeed-key"
        assert call.kwargs["params"]["url"] == "https://example.com/running-shoes"
        strategies.add(call.kwargs["params"]["strategy"])
    assert strategies == {"mobile", "desktop"}

    found = checks_by_id(result)
    assert result.score == 91
    assert found["lh_performance"].status == Status.GOOD
    assert found["lh_performance"].value == "91/100"
    assert found["crux_overall"].status == Status.GOOD


@override_settings(GOOGLE_PAGESPEED_API_KEY="test-pagespeed-key")
def test_performance_analyzer_degrades_when_pagespeed_errors():
    with patch("apps.seo_checker.analyzers.performance.httpx.get") as mocked:
        mocked.side_effect = httpx.ConnectError("blocked in tests")
        result = PerformanceAnalyzer().analyze(make_page_data("<html></html>"))

    assert result.score == 0
    assert checks_by_id(result)["psi_error"].status == Status.WARNING
    assert mocked.call_count == 2


def _ai_payload() -> str:
    return json.dumps(
        {
            "executive_summary": "The page is a focused running-shoe guide.",
            "content_quality_score": 82,
            "content_verdict": "good",
            "content_issues": ["The intro never names a brand."],
            "suggested_title": "Running Shoes: Fit, Cushioning, and Durability",
            "suggested_meta_description": "Compare running-shoe fit and cushioning before you buy.",
            "top_recommendations": [
                {
                    "priority": 2,
                    "area": "Content",
                    "action": "Name the shoe models in the opening paragraph.",
                    "expected_impact": "High",
                }
            ],
        }
    )


def test_ai_insights_skips_openai_without_a_key():
    with patch(
        "apps.seo_checker.analyzers.ai_insights.openai.OpenAI",
        side_effect=AssertionError("OpenAI client must not be constructed"),
    ):
        result, extras = AIInsightsAnalyzer().analyze(make_page_data("<html></html>"))

    assert extras == {}
    assert checks_by_id(result)["ai_unavailable"].status == Status.INFO


@override_settings(OPENAI_API_KEY="test-openai-key")
def test_ai_insights_parses_a_mocked_completion():
    message = MagicMock()
    message.content = _ai_payload()
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response

    with patch(
        "apps.seo_checker.analyzers.ai_insights.openai.OpenAI",
        return_value=client,
    ) as constructor:
        result, extras = AIInsightsAnalyzer().analyze(
            make_page_data(_meta_html("T" * 55, "D" * 150)),
            rule_based_failures=["[Meta] Title Length: too long"],
        )

    constructor.assert_called_once_with(api_key="test-openai-key")
    client.chat.completions.create.assert_called_once()
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-5.3"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert "too long" in kwargs["messages"][1]["content"]

    found = checks_by_id(result)
    assert extras["executive_summary"].startswith("The page is")
    assert extras["content_quality_score"] == 82
    assert extras["content_verdict"] == "good"
    assert extras["top_recommendations"][0]["area"] == "Content"
    assert found["ai_content_score"].status == Status.GOOD
    assert found["ai_suggested_title"].value.startswith("Running Shoes")


def test_parse_response_strips_markdown_fences():
    parsed = _parse_response('```json\n{"content_quality_score": 10}\n```')
    assert parsed == {"content_quality_score": 10}
