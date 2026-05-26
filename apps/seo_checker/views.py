"""
seo_checker/views.py
"""
from __future__ import annotations
from django.shortcuts import render
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny

from .models import SeoCheck, CheckStatus
from .serializers import SeoCheckSerializer, SeoCheckCreateSerializer
from .tasks import run_seo_check


def index(request):
    """Render the SEO checker SPA."""
    return render(request, "seo_checker/index.html")


class SeoCheckCreateView(APIView):
    """
    POST /api/seo-check/
    Body: {"url": "https://example.com"}
    Returns the check ID immediately; analysis runs async via Celery.
    """
    permission_classes = [AllowAny]
    throttle_scope     = "seo_check"

    def post(self, request):
        ser = SeoCheckCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response({"error": ser.errors}, status=status.HTTP_400_BAD_REQUEST)

        url = ser.validated_data["url"]

        # Basic rate-limit: one active check per IP at a time
        ip = _get_client_ip(request)
        if SeoCheck.objects.filter(
            ip_address=ip,
            status__in=[CheckStatus.PENDING, CheckStatus.RUNNING],
            created_at__gte=timezone.now() - timezone.timedelta(seconds=60),
        ).exists():
            return Response(
                {"error": "A check is already in progress. Please wait."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        check = SeoCheck.objects.create(
            url        = url,
            ip_address = ip,
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:512],
        )

        task = run_seo_check.delay(str(check.id))
        check.celery_task_id = task.id
        check.save(update_fields=["celery_task_id"])

        return Response(
            {"id": str(check.id), "status": check.status},
            status=status.HTTP_201_CREATED,
        )


class SeoCheckDetailView(APIView):
    """
    GET /api/seo-check/<uuid>/
    Returns the current state of a check, including full category results
    when status == 'complete'.
    """
    permission_classes = [AllowAny]

    def get(self, request, check_id):
        try:
            check = SeoCheck.objects.prefetch_related("categories").get(id=check_id)
        except (SeoCheck.DoesNotExist, ValueError):
            return Response({"error": "Check not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(SeoCheckSerializer(check).data)


def _get_client_ip(request) -> str | None:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
