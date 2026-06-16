from django.contrib import admin

from .models import ExportRecord, Lead, SearchCampaign


@admin.register(SearchCampaign)
class SearchCampaignAdmin(admin.ModelAdmin):
    list_display = ("query", "location", "status", "total_found", "created_at")
    list_filter = ("status", "sources", "created_at")
    search_fields = ("query", "location", "business_type")


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "category", "phone", "website", "lead_score", "duplicate_count", "is_qualified")
    list_filter = ("source", "has_hmo_signal", "is_qualified", "campaign")
    search_fields = ("name", "address", "phone", "email", "website", "category")


@admin.register(ExportRecord)
class ExportRecordAdmin(admin.ModelAdmin):
    list_display = ("campaign", "export_format", "row_count", "destination", "created_at")
    list_filter = ("export_format", "created_at")
