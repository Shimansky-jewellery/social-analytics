from django.urls import path
from . import views

app_name = "analytics"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("import/", views.import_sheet, name="import_sheet"),
    path("channels/", views.channel_comparison, name="comparison"),
    path("insights/", views.insights_page, name="insights"),
]
