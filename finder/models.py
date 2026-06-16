from django.db import models
from django.utils import timezone


class SearchCampaign(models.Model):
    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    query = models.CharField(max_length=255)
    location = models.CharField(max_length=160, blank=True)
    business_type = models.CharField(max_length=120, blank=True)
    sources = models.JSONField(default=list, blank=True)
    llm_enabled = models.BooleanField(default=False)
    search_plan = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    total_found = models.PositiveIntegerField(default=0)
    source_counts = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        bits = [self.query]
        if self.location:
            bits.append(self.location)
        return " - ".join(bits)


class Lead(models.Model):
    SOURCE_CHOICES = [
        ("google_places", "Google Places"),
        ("openstreetmap", "OpenStreetMap"),
    ]

    campaign = models.ForeignKey(SearchCampaign, on_delete=models.CASCADE, related_name="leads")
    source = models.CharField(max_length=40, choices=SOURCE_CHOICES)
    source_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=80, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    category = models.CharField(max_length=160, blank=True)
    rating = models.FloatField(null=True, blank=True)
    review_count = models.PositiveIntegerField(default=0)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    map_url = models.URLField(blank=True)
    dedupe_key = models.CharField(max_length=255, db_index=True, blank=True)
    duplicate_count = models.PositiveIntegerField(default=0)
    has_hmo_signal = models.BooleanField(default=False)
    is_qualified = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    lead_score = models.PositiveIntegerField(default=0)
    tags = models.JSONField(default=list, blank=True)
    socials = models.JSONField(default=dict, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-lead_score", "name"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "source", "source_id"], name="unique_campaign_source_lead")
        ]

    def __str__(self):
        return self.name


class ExportRecord(models.Model):
    FORMAT_CHOICES = [
        ("csv", "CSV"),
        ("xlsx", "Excel XLSX"),
        ("json", "JSON"),
    ]

    campaign = models.ForeignKey(SearchCampaign, on_delete=models.CASCADE, related_name="exports")
    export_format = models.CharField(max_length=30, choices=FORMAT_CHOICES)
    row_count = models.PositiveIntegerField(default=0)
    destination = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_export_format_display()} export for {self.campaign}"
