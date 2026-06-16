from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .services import ProviderResult, enrich_google_place_details_bulk


class GooglePlaceDetailsTests(SimpleTestCase):
    @override_settings(
        GOOGLE_API_KEY="test-google-key",
        GOOGLE_PLACE_DETAILS_ENABLED=True,
        GOOGLE_DETAILS_WORKERS=1,
        GOOGLE_DETAILS_TIMEOUT=1,
    )
    @patch("finder.services.request_json")
    def test_enriches_google_results_with_phone_and_website(self, request_json):
        request_json.return_value = {
            "status": "OK",
            "result": {
                "international_phone_number": "+234 801 234 5678",
                "website": "https://examplehospital.test",
                "url": "https://maps.google.com/?cid=123",
            },
        }
        result = ProviderResult(
            source="google_places",
            source_id="place-123",
            name="Example Hospital",
        )

        enriched = enrich_google_place_details_bulk([result])[0]

        self.assertEqual(enriched.phone, "+234 801 234 5678")
        self.assertEqual(enriched.website, "https://examplehospital.test")
        self.assertEqual(enriched.map_url, "https://maps.google.com/?cid=123")
