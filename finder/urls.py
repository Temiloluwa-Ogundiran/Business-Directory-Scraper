from django.urls import path
from .views import campaign_detail, enrich_campaign_contacts, export_leads, load_next_results, search_business

urlpatterns = [
    path('', search_business, name="search_business"),
    path("campaigns/<int:campaign_id>/", campaign_detail, name="campaign_detail"),
    path("campaigns/<int:campaign_id>/next/", load_next_results, name="load_next_results"),
    path("campaigns/<int:campaign_id>/contacts/", enrich_campaign_contacts, name="enrich_campaign_contacts"),
    path("campaigns/<int:campaign_id>/export/<str:export_format>/", export_leads, name="export_leads"),
]
