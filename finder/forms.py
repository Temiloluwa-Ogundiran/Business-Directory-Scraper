from django import forms

class BusinessSearchForm(forms.Form):
    query = forms.CharField(label='Search', max_length=100, required=False)
    location = forms.CharField(label='Location (City/State)', max_length=100, required=False)
    business_type = forms.CharField(label='Business Type', max_length=100, required=False)