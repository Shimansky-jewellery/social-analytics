from django.contrib import admin
from .models import SocialMetric

@admin.register(SocialMetric)
class SocialMetricAdmin(admin.ModelAdmin):
    list_display = ("channel", "period", "views", "reach", "engagement_rate", "leads", "imported_at")
    list_filter = ("channel", "period")
    search_fields = ("channel", "period", "top_performing_post")
