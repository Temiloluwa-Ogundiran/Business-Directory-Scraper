import requests

API_KEY = ""
BASE_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# Example: Searching for restaurants near Lagos, Nigeria
params = {
    "location": "6.5244,3.3792",  # Latitude, Longitude of Lagos
    "radius": 5000,  # Search within 5km
    "type": "restaurant",  # Type of place
    "keyword": "restaurant",  # Additional search keyword
    "key": API_KEY
}

response = requests.get(BASE_URL, params=params)

if response.status_code == 200:
    data = response.json()
    for place in data.get("results", []):
        name = place.get("name", "N/A")
        address = place.get("vicinity", "N/A")
        print(f"Name: {name}, Address: {address}")
else:
    print(f"Error: {response.status_code}, {response.text}")