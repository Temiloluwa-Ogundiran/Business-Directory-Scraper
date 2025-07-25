import json
import requests
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from .forms import BusinessSearchForm
from django.conf import settings

def search_business(request):
    results = []
    if request.method == 'POST':
        form = BusinessSearchForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data.get('query', '')
            location = form.cleaned_data.get('location', '')
            business_type = form.cleaned_data.get('business_type', '')

            # Build the API URL based on provided parameters
            api_url = "https://maps.googleapis.com/maps/api/place/textsearch/json?"
            if query:
                api_url += f"query={query}+"
                if location:
                    api_url += f"in+{location}+"
                if business_type:
                    api_url += f"&type={business_type}+"
            elif business_type:
                api_url += f"query={business_type}+"
                if location:
                    api_url += f"in+{location}+"
            else:
                api_url += f"query=business in {location}, Nigeria+"
            api_url += f"&key={settings.GOOGLE_API_KEY}"

            response = requests.get(api_url)
            results = response.json().get('results', [])
    else:
        form = BusinessSearchForm()

    return render(request, 'finder/search.html', {'form': form, 'results': results})


def download_json(request):
    results = []
    if request.method == 'POST':
        form = BusinessSearchForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data.get('query', '')
            location = form.cleaned_data.get('location', '')
            business_type = form.cleaned_data.get('business_type', '')

            # Build the API URL based on provided parameters
            api_url = "https://maps.googleapis.com/maps/api/place/textsearch/json?"
            if query:
                api_url += f"query={query}+"
                if location:
                    api_url += f"in+{location}+"
                if business_type:
                    api_url += f"&type={business_type}+"
            elif business_type:
                api_url += f"query={business_type}+"
                if location:
                    api_url += f"in+{location}+"
            else:
                api_url += f"query=business in {location}, Nigeria+"
            api_url += f"&key={settings.GOOGLE_API_KEY}"

            response = requests.get(api_url)
            results = response.json().get('results', [])

            # Create a JSON file response
            json_data = json.dumps(results, indent=4)
            response = HttpResponse(json_data, content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="{query.replace(" ", "_")}_results.json"'
            return response

    return JsonResponse({'error': 'Invalid request'}, status=400)