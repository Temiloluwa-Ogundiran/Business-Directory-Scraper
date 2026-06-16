from django import forms


class BusinessSearchForm(forms.Form):
    query = forms.CharField(
        label="Search phrase",
        max_length=255,
        required=True,
        help_text='Try natural searches like "Hospitals in Lagos with HMO".',
        widget=forms.TextInput(attrs={"placeholder": "Hospitals in Lagos with HMO"}),
    )
    location = forms.CharField(
        label="Location override",
        max_length=160,
        required=False,
        help_text="Optional. Useful when the phrase does not already include a location.",
        widget=forms.TextInput(attrs={"placeholder": "Lagos, Nigeria"}),
    )
    business_type = forms.CharField(
        label="Business type",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "hospital, clinic, restaurant"}),
    )
    llm_variants = forms.IntegerField(
        label="Search depth",
        min_value=1,
        max_value=25,
        initial=10,
        help_text="Number of focused search phrases the AI planner can create.",
    )
    google_pages = forms.IntegerField(
        label="Google result pages",
        min_value=1,
        max_value=3,
        initial=1,
        help_text="Google Places exposes up to 3 text-search pages per query.",
    )

class LeadFilterForm(forms.Form):
    q = forms.CharField(label="Filter", max_length=120, required=False)
    missing_website = forms.BooleanField(label="No website", required=False)
    has_phone = forms.BooleanField(label="Has phone", required=False)
    has_email = forms.BooleanField(label="Has email", required=False)
    duplicates = forms.BooleanField(label="Duplicates", required=False)
