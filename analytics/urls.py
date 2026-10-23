from django.urls import path
from . import views

app_name = "analytics"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("import/", views.import_sheet, name="import_sheet"),
    path("channels/", views.channel_comparison, name="comparison"),
    path("insights/", views.insights_page, name="insights"),
    path("ads/", views.ads_page, name="ads"),
    path("ads/import/", views.import_ads, name="import_ads"),
    path("audience/", views.audience_page, name="audience"),
    path("audience/import/", views.import_audience, name="import_audience"),
    path("ads/clear-data/", views.clear_ads_data, name="clear_ads_data"),
    path("audience/clear-data/", views.clear_audience_data, name="clear_audience_data"),
    path("clear-data/", views.clear_data, name="clear_data"),
]
