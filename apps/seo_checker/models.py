"""
seo_checker/models.py — Database models for storing SEO check results.
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class CheckStatus(models.TextChoices):
    PENDING  = "pending",  _("Pending")
    RUNNING  = "running",  _("Running")
    COMPLETE = "complete", _("Complete")
    FAILED   = "failed",   _("Failed")


class SeoCheck(models.Model):
    """
    One row per URL submitted for analysis.
    Stores top-level metadata; detailed results live in CheckCategory rows.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url             = models.URLField(max_length=2048, db_index=True)
    final_url       = models.URLField(max_length=2048, blank=True)
    status          = models.CharField(
        max_length=20, choices=CheckStatus.choices, default=CheckStatus.PENDING
    )
    overall_score   = models.SmallIntegerField(null=True, blank=True)
    page_title      = models.CharField(max_length=512, blank=True)
    celery_task_id  = models.CharField(max_length=255, blank=True)
    error_message   = models.TextField(blank=True)

    # AI-generated insights (populated after GPT-5.3 analysis)
    ai_summary      = models.TextField(blank=True, help_text="Executive summary from GPT-5.3.")
    ai_suggestions  = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Structured AI output: suggested_title, suggested_meta_description, "
            "top_recommendations, content_quality_score, content_verdict."
        ),
    )

    # Request metadata
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    user_agent      = models.CharField(max_length=512, blank=True)

    created_at      = models.DateTimeField(auto_now_add=True)
    completed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering            = ["-created_at"]
        verbose_name        = "SEO Check"
        verbose_name_plural = "SEO Checks"
        indexes             = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["celery_task_id"]),
        ]

    def __str__(self):
        return f"{self.url} [{self.status}] score={self.overall_score}"

    @property
    def duration_seconds(self) -> float | None:
        if self.created_at and self.completed_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None

    @property
    def score_label(self) -> str:
        if self.overall_score is None:
            return "N/A"
        if self.overall_score >= 80:
            return "Good"
        if self.overall_score >= 50:
            return "Needs Improvement"
        return "Poor"


class CheckCategory(models.Model):
    """
    One row per analysis category per SeoCheck.
    The detailed check list is stored as JSON in `checks_data`.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seo_check    = models.ForeignKey(
        SeoCheck, on_delete=models.CASCADE, related_name="categories"
    )
    category     = models.CharField(max_length=40, db_index=True)
    display_name = models.CharField(max_length=80)
    score        = models.SmallIntegerField()
    checks_data  = models.JSONField(
        default=list,
        help_text="Serialised list of Check dataclass instances."
    )

    class Meta:
        unique_together     = ("seo_check", "category")
        verbose_name        = "Check Category"
        verbose_name_plural = "Check Categories"
        ordering            = ["category"]

    def __str__(self):
        return f"{self.seo_check.url} — {self.display_name} ({self.score})"

    @property
    def score_status(self) -> str:
        if self.score >= 80:
            return "good"
        if self.score >= 50:
            return "warning"
        return "error"
