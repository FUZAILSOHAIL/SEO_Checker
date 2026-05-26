from django.urls import path
from . import views

app_name = "seo_checker"

urlpatterns = [
    path("",                           views.index,                name="index"),
    path("api/seo-check/",             views.SeoCheckCreateView.as_view(), name="create"),
    path("api/seo-check/<uuid:check_id>/", views.SeoCheckDetailView.as_view(), name="detail"),
]
