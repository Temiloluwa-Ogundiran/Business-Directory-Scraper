from django.urls import path
from .views import search_business, download_json

urlpatterns = [
    path('', search_business, name="search_business"),
    path('download/', download_json, name='download_json'),
]