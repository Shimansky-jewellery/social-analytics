from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import AdPerformance, AudienceMetric, SocialMetric


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
        insights = self.client.get(reverse("analytics:insights"))
        self.assertContains(insights, "Channel highlights")
        self.assertContains(insights, "Clear &amp; return to dashboard")
        self.assertContains(
            insights,
            f'href="{reverse("analytics:dashboard")}"',
        )
        filtered = self.client.get(
            reverse("analytics:dashboard"),
            {"start_date": "2026-09-01", "end_date": "2026-09-01"},
        )
        self.assertEqual(filtered.context["kpis"]["views"], 200)

    def test_imported_channel_name_is_json_escaped_in_dashboard(self):
        SocialMetric.objects.create(channel="</script>", period="2026-09-01", views=2)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertContains(response, r"\u003C/script\u003E")

    def test_clear_data_post_removes_all_imported_records_and_returns_to_empty_dashboard(self):
        SocialMetric.objects.create(channel="Instagram", period="2026-09", views=100)
        SocialMetric.objects.create(channel="TikTok", period="2026-09", views=200)

        response = self.client.post(reverse("analytics:clear_data"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("analytics:dashboard"))
        self.assertEqual(SocialMetric.objects.count(), 0)
        dashboard = self.client.get(response.url)
        self.assertContains(dashboard, "Your insights start here")
        self.assertContains(dashboard, "Cleared 2 imported social media record(s).")

    def test_clear_data_rejects_get_requests(self):
        SocialMetric.objects.create(channel="Instagram", period="2026-09", views=100)

        response = self.client.get(reverse("analytics:clear_data"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(SocialMetric.objects.count(), 1)

    def test_ctr_is_averaged_and_shown_as_percentage(self):
        SocialMetric.objects.create(channel="Instagram", period="2026-09-01", ctr=1.5)
        SocialMetric.objects.create(channel="Instagram", period="2026-10-01", ctr=2.5)
        dashboard = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(dashboard.context["kpis"]["ctr"], 2.0)
        self.assertContains(dashboard, "Avg. CTR")
        self.assertContains(dashboard, "2.00")
        self.assertContains(dashboard, '<span class="unit">%</span>', html=True)
        comparison = self.client.get(reverse("analytics:comparison"))
        ctr_metric = next(item for item in comparison.context["metrics"] if item["key"] == "ctr")
        self.assertEqual(ctr_metric["values"][0]["value"], 2.0)
        self.assertContains(comparison, "2.00%")

    def test_null_ctr_displays_dash(self):
        SocialMetric.objects.create(channel="Instagram", period="2026-09-01", ctr=None)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertIsNone(response.context["kpis"]["ctr"])
        self.assertContains(response, "Avg. CTR")


ADS_HEADERS = (
    "Platform,Period Start,Period End,Ad Name,Ad Set,Status,Amount Spent (ZAR),"
    "Impressions,Reach,Frequency,CPM (ZAR),Results,Result Type,Cost per Result (ZAR),"
    "Quality Ranking,Engagement Rate Ranking,Conversion Rate Ranking\n"
)

ADS_ROW = (
    "Meta,2026-09-01,2026-09-30,Autumn campaign,Prospecting,Active,1500.50,"
    "10000,8000,1.25,150.05,25,Purchase,60.02,Above average,Average,Above average\n"
)


class AdCsvImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ads-importer", password="test-password")
        self.client.force_login(self.user)

    def test_imports_valid_ads_csv_row(self):
        response = self.client.post(
            reverse("analytics:import_ads"),
            {"ads_csv_file": csv_upload(ADS_HEADERS + ADS_ROW, "ads.csv")},
        )
        self.assertContains(response, "1")
        ad = AdPerformance.objects.get()
        self.assertEqual(ad.platform, "Meta")
        self.assertEqual(str(ad.amount_spent), "1500.50")
        self.assertEqual(ad.impressions, 10000)

    def test_duplicate_ads_are_skipped_without_overwriting(self):
        content = ADS_HEADERS + ADS_ROW
        self.client.post(reverse("analytics:import_ads"), {"ads_csv_file": csv_upload(content, "ads.csv")})
        response = self.client.post(
            reverse("analytics:import_ads"),
            {"ads_csv_file": csv_upload(content, "ads.csv")},
        )
        self.assertContains(response, "Skipped (duplicates)")
        self.assertEqual(AdPerformance.objects.count(), 1)
        self.assertEqual(AdPerformance.objects.get().amount_spent, 1500.50)

    def test_blank_ads_numeric_values_are_saved_as_null(self):
        blank_row = (
            "Meta,2026-09-01,2026-09-30,Autumn campaign,,,,,-,-,,,-,,,\n"
        )
        response = self.client.post(
            reverse("analytics:import_ads"),
            {"ads_csv_file": csv_upload(ADS_HEADERS + blank_row, "ads.csv")},
        )
        self.assertContains(response, "1")
        ad = AdPerformance.objects.get()
        for field in (
            "amount_spent", "impressions", "reach", "frequency", "cpm",
            "results", "cost_per_result",
        ):
            self.assertIsNone(getattr(ad, field), field)

    def test_missing_required_ads_header_is_rejected(self):
        incomplete = ADS_HEADERS.replace("Period Start,", "")
        response = self.client.post(
            reverse("analytics:import_ads"),
            {"ads_csv_file": csv_upload(incomplete + ADS_ROW, "ads.csv")},
        )
        self.assertContains(response, "missing headers: Period Start")
        self.assertEqual(AdPerformance.objects.count(), 0)

    def test_ads_page_and_import_are_public(self):
        self.client.logout()
        page = self.client.get(reverse("analytics:ads"))
        upload = self.client.get(reverse("analytics:import_ads"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(upload.status_code, 200)
        response = self.client.post(
            reverse("analytics:import_ads"),
            {"ads_csv_file": csv_upload(ADS_HEADERS + ADS_ROW, "ads.csv")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AdPerformance.objects.count(), 1)

    def test_ads_import_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("analytics:import_ads"),
            {"ads_csv_file": csv_upload(ADS_HEADERS + ADS_ROW, "ads.csv")},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AdPerformance.objects.count(), 0)

    def test_ads_page_displays_ad_metrics_and_totals(self):
        AdPerformance.objects.create(
            platform="Meta",
            period_start="2026-09-01",
            period_end="2026-09-30",
            ad_name="Autumn campaign",
            amount_spent=Decimal("1500.50"),
            impressions=10000,
            reach=8000,
            frequency=1.25,
            cpm=Decimal("150.05"),
            results=25,
            quality_ranking="Above average",
        )
        response = self.client.get(reverse("analytics:ads"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_spend"], Decimal("1500.50"))
        self.assertEqual(response.context["total_impressions"], 10000)
        self.assertContains(response, "Autumn campaign")
        self.assertContains(response, "Total spend")

    def test_clear_ads_data_deletes_only_ads_and_requires_post(self):
        ad = AdPerformance.objects.create(
            platform="Meta",
            period_start="2026-09-01",
            period_end="2026-09-30",
            ad_name="Autumn campaign",
        )
        social = SocialMetric.objects.create(channel="Instagram", period="2026-09")

        response = self.client.get(reverse("analytics:clear_ads_data"))
        self.assertEqual(response.status_code, 405)
        response = self.client.post(reverse("analytics:clear_ads_data"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("analytics:ads"))
        self.assertFalse(AdPerformance.objects.filter(pk=ad.pk).exists())
        self.assertTrue(SocialMetric.objects.filter(pk=social.pk).exists())

    def test_clear_ads_data_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(reverse("analytics:clear_ads_data"))
        self.assertEqual(response.status_code, 403)


AUDIENCE_HEADERS = "Channel,Snapshot Date,Category,Label,Segment,Value,Unit\n"
AUDIENCE_ROW = "Instagram,2026-10-01,Country,South Africa,,35.5,%\n"


class AudienceCsvImportTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="audience-importer", password="test-password")
        self.client.force_login(user)

    def test_imports_valid_audience_row(self):
        response = self.client.post(
            reverse("analytics:import_audience"),
            {"audience_csv_file": csv_upload(AUDIENCE_HEADERS + AUDIENCE_ROW, "audience.csv")},
        )
        self.assertContains(response, "Created")
        metric = AudienceMetric.objects.get()
        self.assertEqual(metric.channel, "Instagram")
        self.assertEqual(metric.label, "South Africa")
        self.assertEqual(metric.value, 35.5)

    def test_duplicate_audience_rows_are_skipped_without_overwriting(self):
        content = AUDIENCE_HEADERS + AUDIENCE_ROW
        self.client.post(
            reverse("analytics:import_audience"),
            {"audience_csv_file": csv_upload(content, "audience.csv")},
        )
        response = self.client.post(
            reverse("analytics:import_audience"),
            {"audience_csv_file": csv_upload(content, "audience.csv")},
        )
        self.assertContains(response, "Skipped (duplicates)")
        self.assertEqual(AudienceMetric.objects.count(), 1)
        self.assertEqual(AudienceMetric.objects.get().value, 35.5)

    def test_na_label_is_preserved_as_text(self):
        content = AUDIENCE_HEADERS + "Instagram,2026-10-01,Country,NA,,1.2, %\n"
        self.client.post(
            reverse("analytics:import_audience"),
            {"audience_csv_file": csv_upload(content, "audience.csv")},
        )
        self.assertEqual(AudienceMetric.objects.get().label, "NA")

    def test_missing_required_audience_header_is_rejected(self):
        incomplete = AUDIENCE_HEADERS.replace("Category,", "")
        response = self.client.post(
            reverse("analytics:import_audience"),
            {"audience_csv_file": csv_upload(incomplete + AUDIENCE_ROW, "audience.csv")},
        )
        self.assertContains(response, "missing headers: Category")
        self.assertEqual(AudienceMetric.objects.count(), 0)

    def test_audience_page_and_import_are_public_and_csrf_protected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("analytics:audience")).status_code, 200)
        self.assertEqual(self.client.get(reverse("analytics:import_audience")).status_code, 200)
        response = self.client.post(
            reverse("analytics:import_audience"),
            {"audience_csv_file": csv_upload(AUDIENCE_HEADERS + AUDIENCE_ROW, "audience.csv")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AudienceMetric.objects.count(), 1)

        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("analytics:import_audience"),
            {"audience_csv_file": csv_upload(AUDIENCE_HEADERS + AUDIENCE_ROW, "audience.csv")},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AudienceMetric.objects.count(), 1)

    def test_audience_page_defaults_to_latest_snapshot(self):
        AudienceMetric.objects.create(
            channel="Instagram",
            snapshot_date="2026-09-01",
            category="Country",
            label="Namibia",
            value=20,
            unit="%",
        )
        AudienceMetric.objects.create(
            channel="Instagram",
            snapshot_date="2026-10-01",
            category="Country",
            label="South Africa",
            value=35,
            unit="%",
        )
        response = self.client.get(reverse("analytics:audience"))
        self.assertEqual(response.context["selected_snapshot"], "2026-10-01")
        self.assertContains(response, "South Africa")
        self.assertContains(response, "Top locations only")

    def test_clear_audience_data_deletes_only_audience_and_requires_post(self):
        audience = AudienceMetric.objects.create(
            channel="Instagram",
            snapshot_date="2026-10-01",
            category="Country",
            label="South Africa",
            value=35,
            unit="%",
        )
        social = SocialMetric.objects.create(channel="Instagram", period="2026-10")

        response = self.client.get(reverse("analytics:clear_audience_data"))
        self.assertEqual(response.status_code, 405)
        response = self.client.post(reverse("analytics:clear_audience_data"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("analytics:audience"))
        self.assertFalse(AudienceMetric.objects.filter(pk=audience.pk).exists())
        self.assertTrue(SocialMetric.objects.filter(pk=social.pk).exists())

    def test_clear_audience_data_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(reverse("analytics:clear_audience_data"))
        self.assertEqual(response.status_code, 403)
