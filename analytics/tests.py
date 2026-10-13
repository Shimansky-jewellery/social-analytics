from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import SocialMetric


HEADERS = (
    "Channel,Period,Follower Growth,Reach,Views,Engagement Rate (%),Content Interactions,"
    "Click-Through Rate (CTR) (%),Profile Visits,Link Clicks,DMs/Leads Generated,Top Performing Post\n"
)


def csv_upload(contents, filename="metrics.csv"):
    return SimpleUploadedFile(filename, contents.encode("utf-8"), content_type="text/csv")


class CsvImportTests(TestCase):
    def test_imports_csv_and_preserves_blank_metrics(self):
        contents = HEADERS + (
            "Instagram,2026-09,15,1200,2400,5.4%,38,2.1%,75,12,4,Launch post\n"
            "TikTok,2026-10,,,,,,,,,,\n"
        )
        response = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload(contents)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2")
        self.assertContains(response, "View analytics dashboard")
        self.assertEqual(SocialMetric.objects.count(), 2)
        instagram = SocialMetric.objects.get(channel="Instagram")
        self.assertEqual(instagram.period, "2026-09-01")
        self.assertEqual(instagram.engagement_rate, 5.4)
        self.assertEqual(instagram.ctr, 2.1)
        tiktok = SocialMetric.objects.get(channel="TikTok")
        self.assertIsNone(tiktok.views)

    def test_duplicate_upload_skips_existing_rows_without_deleting_other_data(self):
        SocialMetric.objects.create(channel="Other", period="2026-08", views=88)
        contents = HEADERS + "Instagram,2026-09,15,1200,2400,5.4%,38,2.1%,75,12,4,Launch post\n"
        self.client.post(reverse("analytics:import_sheet"), {"csv_file": csv_upload(contents)})
        response = self.client.post(reverse("analytics:import_sheet"), {"csv_file": csv_upload(contents)})
        self.assertContains(response, "1")
        self.assertContains(response, "Skipped (duplicates)")
        self.assertEqual(SocialMetric.objects.count(), 2)
        self.assertTrue(SocialMetric.objects.filter(channel="Other").exists())

    def test_duplicate_detection_matches_legacy_period_format(self):
        SocialMetric.objects.create(channel="Instagram", period="2026-09", views=100)
        contents = HEADERS + "Instagram,2026-09,15,1200,2400,5.4%,38,2.1%,75,12,4,Launch post\n"
        response = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload(contents)},
        )
        self.assertContains(response, "Skipped (duplicates)")
        self.assertEqual(SocialMetric.objects.count(), 1)
        self.assertEqual(SocialMetric.objects.get().views, 100)

    def test_rejects_missing_columns_and_unsupported_populated_columns(self):
        missing = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload("Channel,Reach\nInstagram,4\n")},
        )
        self.assertContains(missing, "Missing required columns")
        unsupported = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload(HEADERS.rstrip() + ",Unmapped\n" +
                                    "Instagram,2026-09,1,2,3,4,5,6,7,8,9,Post,extra\n")},
        )
        self.assertContains(unsupported, "Unsupported columns contain data")
        self.assertEqual(SocialMetric.objects.count(), 0)

    def test_rejects_empty_malformed_and_wrong_extension_files(self):
        empty = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload("")},
        )
        self.assertContains(empty, "empty")
        malformed = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload("Channel,Period,Reach\nInstagram,2026-09,2\nTikTok,2026-10,3,extra\n")},
        )
        self.assertContains(malformed, "could not be read as a CSV")
        wrong_extension = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload(HEADERS + "Instagram,2026-09,,,,,,,,,,\n", "metrics.txt")},
        )
        self.assertContains(wrong_extension, ".csv extension")
        self.assertEqual(SocialMetric.objects.count(), 0)

    def test_invalid_rows_are_reported_while_valid_rows_import(self):
        contents = HEADERS + (
            "Instagram,2026-09,15,1200,2400,5.4%,38,2.1%,75,12,4,Launch post\n"
            "Facebook,2026-10,bad,1200,2400,5.4%,38,2.1%,75,12,4,Other post\n"
            ",2026-10,1,2,3,4,5,6,7,8,9,Missing channel\n"
        )
        response = self.client.post(
            reverse("analytics:import_sheet"),
            {"csv_file": csv_upload(contents)},
        )
        self.assertContains(response, "Imported")
        self.assertContains(response, "Rejected")
        self.assertContains(response, "CSV line 3")
        self.assertEqual(SocialMetric.objects.count(), 1)

    def test_dashboard_comparison_and_insights_render_imported_metrics(self):
        SocialMetric.objects.create(
            channel="Instagram",
            period="2026-09-01",
            views=200,
            reach=120,
            follower_growth=10,
            engagement_rate=5.5,
            content_interactions=20,
            profile_visits=30,
            link_clicks=4,
            leads=3,
        )
        SocialMetric.objects.create(
            channel="Instagram",
            period="2026-10-01",
            views=400,
            reach=180,
            follower_growth=20,
            engagement_rate=8.5,
            content_interactions=30,
            profile_visits=40,
            link_clicks=6,
            leads=5,
        )
        dashboard = self.client.get(reverse("analytics:dashboard"))
        self.assertContains(dashboard, "Total views")
        self.assertContains(dashboard, 'href="/static/analytics/css/app.css"')
        self.assertContains(dashboard, "Profile visits")
        self.assertEqual(dashboard.context["kpis"]["views"], 600)
        self.assertEqual(dashboard.context["kpis"]["engagement_rate"], 7.0)
        self.assertContains(self.client.get(reverse("analytics:comparison")), "Reported performance")
        self.assertContains(self.client.get(reverse("analytics:insights")), "Channel highlights")
        filtered = self.client.get(
            reverse("analytics:dashboard"),
            {"start_date": "2026-09-01", "end_date": "2026-09-01"},
        )
        self.assertEqual(filtered.context["kpis"]["views"], 200)

    def test_imported_channel_name_is_json_escaped_in_dashboard(self):
        SocialMetric.objects.create(channel="</script>", period="2026-09-01", views=2)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertContains(response, r"\u003C/script\u003E")
