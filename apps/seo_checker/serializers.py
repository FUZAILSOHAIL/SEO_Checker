"""
seo_checker/serializers.py
"""
from rest_framework import serializers
from .models import SeoCheck, CheckCategory


class CheckCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = CheckCategory
        fields = ("category", "display_name", "score", "checks_data")


class SeoCheckSerializer(serializers.ModelSerializer):
    categories = CheckCategorySerializer(many=True, read_only=True)

    class Meta:
        model  = SeoCheck
        fields = (
            "id", "url", "final_url", "status",
            "overall_score", "page_title",
            "ai_summary", "ai_suggestions",
            "error_message", "created_at", "completed_at",
            "categories",
        )
        read_only_fields = fields


class SeoCheckCreateSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=2048)

    def validate_url(self, value: str) -> str:
        # Normalise scheme
        if not value.startswith(("http://", "https://")):
            value = "https://" + value
        return value.strip()
