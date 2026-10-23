from django.db import models

#mdole to collect social media fields
class SocialMetric(models.Model):
    channel = models.CharField(max_length=100, db_index=True)
    period = models.CharField(max_length=100, db_index=True)
    follower_growth = models.FloatField(default=0, null=True, blank=True)
    reach = models.FloatField(default=0, null=True, blank=True)
    views = models.FloatField(default=0, null=True, blank=True)
    engagement_rate = models.FloatField(default=0, null=True, blank=True)
    content_interactions = models.FloatField(default=0, null=True, blank=True)
    ctr = models.FloatField(default=0, null=True, blank=True)
    profile_visits = models.FloatField(default=0, null=True, blank=True)
    link_clicks = models.FloatField(default=0, null=True, blank=True)
    leads = models.FloatField(default=0, null=True, blank=True)
    top_performing_post = models.TextField(blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["period", "channel"]
        constraints = [
            models.UniqueConstraint(fields=["channel", "period"], name="unique_channel_period")
        ]

    def __str__(self):
        return f"{self.channel} — {self.period}"


class AdPerformance(models.Model):
    platform = models.CharField(max_length=100)
    period_start = models.DateField()
    period_end = models.DateField()
    ad_name = models.CharField(max_length=255)
    ad_set = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, blank=True)
    amount_spent = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    impressions = models.IntegerField(null=True, blank=True)
    reach = models.IntegerField(null=True, blank=True)
    frequency = models.FloatField(null=True, blank=True)
    cpm = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    results = models.FloatField(null=True, blank=True)
    result_type = models.CharField(max_length=255, blank=True)
    cost_per_result = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quality_ranking = models.CharField(max_length=100, blank=True)
    engagement_rate_ranking = models.CharField(max_length=100, blank=True)
    conversion_rate_ranking = models.CharField(max_length=100, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "ad_name", "period_start", "period_end"],
                name="unique_platform_ad_period",
            )
        ]

    def __str__(self):
        return f"{self.platform} — {self.ad_name} ({self.period_start} to {self.period_end})"


class AudienceMetric(models.Model):
    channel = models.CharField(max_length=100)
    snapshot_date = models.DateField()
    category = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    segment = models.CharField(max_length=100, blank=True)
    value = models.FloatField()
    unit = models.CharField(max_length=50)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "snapshot_date", "category", "label", "segment"],
                name="unique_audience_snapshot_segment",
            )
        ]

    def __str__(self):
        return f"{self.channel} — {self.category}: {self.label} ({self.snapshot_date})"
