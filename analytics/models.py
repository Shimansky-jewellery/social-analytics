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
