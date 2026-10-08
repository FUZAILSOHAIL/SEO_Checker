from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from apps.seo_checker.models import CheckCategory, CheckStatus, SeoCheck

pytestmark = pytest.mark.django_db


def _task(task_id: str) -> MagicMock:
    task = MagicMock()
    task.id = task_id
    return task


def test_index_renders_the_checker(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"SEO Analyzer" in response.content


def test_create_enqueues_a_check_without_calling_the_network(api_client):
    with patch(
        "apps.seo_checker.views.run_seo_check.delay",
        return_value=_task("task-123"),
    ) as delay:
        response = api_client.post(
            "/api/seo-check/",
            {"url": "https://example.com"},
            format="json",
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    delay.assert_called_once_with(body["id"])

    check = SeoCheck.objects.get(id=body["id"])
    assert check.url == "https://example.com"
    assert check.celery_task_id == "task-123"
    assert check.status == CheckStatus.PENDING


def test_create_rejects_an_invalid_url(api_client):
    with patch("apps.seo_checker.views.run_seo_check.delay") as delay:
        response = api_client.post(
            "/api/seo-check/",
            {"url": "not a url"},
            format="json",
        )

    assert response.status_code == 400
    assert "url" in response.json()["error"]
    delay.assert_not_called()
    assert SeoCheck.objects.count() == 0


def test_create_rejects_a_second_in_progress_check_from_the_same_ip(api_client):
    SeoCheck.objects.create(
        url="https://example.com/first",
        ip_address="127.0.0.1",
        status=CheckStatus.PENDING,
    )
    with patch("apps.seo_checker.views.run_seo_check.delay") as delay:
        response = api_client.post(
            "/api/seo-check/",
            {"url": "https://example.com/second"},
            format="json",
        )

    assert response.status_code == 429
    delay.assert_not_called()


def test_create_allows_another_ip_while_one_check_is_in_progress(api_client):
    SeoCheck.objects.create(
        url="https://example.com/other",
        ip_address="203.0.113.5",
        status=CheckStatus.PENDING,
    )
    with patch(
        "apps.seo_checker.views.run_seo_check.delay",
        return_value=_task("task-other"),
    ) as delay:
        response = api_client.post(
            "/api/seo-check/",
            {"url": "https://example.com/mine"},
            format="json",
        )

    assert response.status_code == 201
    delay.assert_called_once()


def test_detail_returns_saved_categories(api_client):
    check = SeoCheck.objects.create(
        url="https://example.com",
        final_url="https://example.com/",
        status=CheckStatus.COMPLETE,
        overall_score=84,
        page_title="Example",
        ai_summary="Solid technical SEO.",
    )
    CheckCategory.objects.create(
        seo_check=check,
        category="meta",
        display_name="Meta Information",
        score=91,
        checks_data=[{"id": "title_present", "status": "good"}],
    )

    response = api_client.get(f"/api/seo-check/{check.id}/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["overall_score"] == 84
    assert body["ai_summary"] == "Solid technical SEO."
    assert body["categories"][0]["category"] == "meta"
    assert body["categories"][0]["score"] == 91


def test_detail_returns_404_for_an_unknown_check(api_client):
    response = api_client.get(f"/api/seo-check/{uuid4()}/")
    assert response.status_code == 404
    assert response.json()["error"] == "Check not found."
