import csv
import io
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from django.conf import settings


REQUEST_TIMEOUT = 15
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
SOCIAL_PATTERNS = {
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[^\s\"'<>]+", re.IGNORECASE),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[^\s\"'<>]+", re.IGNORECASE),
    "linkedin": re.compile(r"https?://(?:www\.)?linkedin\.com/[^\s\"'<>]+", re.IGNORECASE),
    "x": re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/[^\s\"'<>]+", re.IGNORECASE),
    "whatsapp": re.compile(r"https?://(?:wa\.me|api\.whatsapp\.com)/[^\s\"'<>]+", re.IGNORECASE),
}


@dataclass
class ProviderResult:
    source: str
    source_id: str
    name: str
    address: str = ""
    phone: str = ""
    website: str = ""
    email: str = ""
    category: str = ""
    rating: float | None = None
    review_count: int = 0
    latitude: float | None = None
    longitude: float | None = None
    map_url: str = ""
    raw_data: dict | None = None


def request_json(url, *, params=None, headers=None, retries=3, delay=1.2):
    last_error = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"Request failed for {url}: {last_error}")


def plan_search_queries_with_llm(query, location="", business_type="", max_variants=5):
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    prompt = {
        "task": "Plan robust business lead searches for Nigeria.",
        "rules": [
            "Return JSON only.",
            "Create focused Google Places style search queries.",
            "Preserve the user's commercial intent and location.",
            "For healthcare/HMO intent include useful Nigerian terms such as HMO, NHIS, health insurance, private hospital, clinic, medical centre where relevant.",
            "Do not invent business names.",
            "Keep query_variants short and searchable.",
        ],
        "input": {
            "query": query,
            "location": location,
            "business_type": business_type,
            "max_variants": max_variants,
        },
        "schema": {
            "intent": "short summary",
            "location": "normalized location",
            "business_type": "normalized category",
            "signals": ["qualifying terms to tag matching leads"],
            "query_variants": [
                {"query": "search phrase", "location": "location", "business_type": "category"}
            ],
        },
    }
    payload = {
        "model": model,
        "input": (
            "You are a search planning assistant for a Nigerian B2B lead-generation tool. "
            "Respond with valid JSON matching the requested schema.\n\n"
            + json.dumps(prompt)
        ),
        "temperature": 0.2,
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    text = _extract_openai_text(data)
    plan = _parse_json_object(text)
    return normalize_search_plan(plan, query, location, business_type, max_variants=max_variants)


def normalize_search_plan(plan, query, location="", business_type="", max_variants=5):
    normalized_location = (plan.get("location") or location or "").strip()
    normalized_type = (plan.get("business_type") or business_type or "").strip()
    signals = [
        str(signal).strip()
        for signal in plan.get("signals", [])
        if str(signal).strip()
    ][:10]
    variants = []
    seen = set()
    for variant in plan.get("query_variants", []):
        if isinstance(variant, str):
            item = {"query": variant, "location": normalized_location, "business_type": normalized_type}
        else:
            item = {
                "query": str(variant.get("query") or "").strip(),
                "location": str(variant.get("location") or normalized_location).strip(),
                "business_type": str(variant.get("business_type") or normalized_type).strip(),
            }
        if not item["query"]:
            continue
        key = (item["query"].lower(), item["location"].lower(), item["business_type"].lower())
        if key in seen:
            continue
        seen.add(key)
        variants.append(item)
        if len(variants) >= max_variants:
            break

    original = {"query": query, "location": location, "business_type": business_type}
    original_key = (query.lower(), location.lower(), business_type.lower())
    if original_key not in seen:
        variants.insert(0, original)

    return {
        "intent": str(plan.get("intent") or query).strip(),
        "location": normalized_location,
        "business_type": normalized_type,
        "signals": signals,
        "query_variants": variants[:max_variants],
    }


def default_search_plan(query, location="", business_type=""):
    return normalize_search_plan(
        {
            "intent": query,
            "location": location,
            "business_type": business_type,
            "signals": _signals_from_text(query),
            "query_variants": [{"query": query, "location": location, "business_type": business_type}],
        },
        query,
        location,
        business_type,
        max_variants=1,
    )


def _signals_from_text(value):
    text = value.lower()
    signals = []
    if "hmo" in text:
        signals.extend(["HMO", "health insurance"])
    if "nhis" in text:
        signals.append("NHIS")
    return signals


def _extract_openai_text(data):
    if data.get("output_text"):
        return data["output_text"]
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    if chunks:
        return "\n".join(chunks)
    raise RuntimeError("OpenAI response did not include text output.")


def _parse_json_object(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise RuntimeError("OpenAI planner returned invalid JSON.")
        return json.loads(match.group(0))


def build_search_phrase(query, location="", business_type=""):
    phrase = " ".join(part.strip() for part in [query, business_type] if part and part.strip())
    if location and location.lower() not in phrase.lower():
        phrase = f"{phrase} in {location}"
    return phrase.strip()


def google_places_search(query, location="", business_type="", pages=1):
    api_key = getattr(settings, "GOOGLE_API_KEY", "") or getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured.")

    phrase = build_search_phrase(query, location, business_type)
    params = {"query": phrase, "key": api_key}
    results = []
    next_page_token = None

    for page in range(max(1, min(int(pages or 1), 3))):
        if next_page_token:
            params = {"pagetoken": next_page_token, "key": api_key}

        payload = _google_text_search(params, uses_page_token=bool(next_page_token))
        status = payload.get("status")
        if status not in {"OK", "ZERO_RESULTS"}:
            raise RuntimeError(payload.get("error_message") or f"Google Places returned {status}")

        for place in payload.get("results", []):
            results.append(_google_place_to_result(place))

        next_page_token = payload.get("next_page_token")
        if not next_page_token:
            break

    return [result for result in results if result.name]


def _google_text_search(params, uses_page_token=False):
    if uses_page_token:
        time.sleep(1.5)
    payload = request_json("https://maps.googleapis.com/maps/api/place/textsearch/json", params=params)
    if payload.get("status") == "INVALID_REQUEST" and uses_page_token:
        return {"status": "ZERO_RESULTS", "results": [], "pagination_warning": "Google page token was not ready."}
    return payload


def _google_place_to_result(place):
    place_id = place.get("place_id", "")
    geometry = place.get("geometry", {}).get("location", {})
    types = place.get("types") or []
    return ProviderResult(
        source="google_places",
        source_id=place_id or f"{place.get('name', '')}:{place.get('formatted_address', '')}",
        name=place.get("name", ""),
        address=place.get("formatted_address", ""),
        phone="",
        website="",
        category=", ".join(types[:3]),
        rating=place.get("rating"),
        review_count=place.get("user_ratings_total") or 0,
        latitude=geometry.get("lat"),
        longitude=geometry.get("lng"),
        map_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else "",
        raw_data={"search": place},
    )


def openstreetmap_search(query, location="", business_type=""):
    phrase = build_search_phrase(query, location, business_type)
    geocode_target = location or phrase
    headers = {"User-Agent": "BusinessDirectoryScraper/1.0"}
    geocode = request_json(
        "https://nominatim.openstreetmap.org/search",
        params={"q": geocode_target, "format": "json", "limit": 1},
        headers=headers,
        retries=2,
    )
    if not geocode:
        return []

    lat = float(geocode[0]["lat"])
    lon = float(geocode[0]["lon"])
    filters = _overpass_filters(query, business_type)
    clauses = "\n".join(f'node(around:15000,{lat},{lon}){flt};way(around:15000,{lat},{lon}){flt};' for flt in filters)
    overpass_query = f"[out:json][timeout:25];({clauses});out center tags 80;"
    payload = request_json(
        "https://overpass-api.de/api/interpreter",
        params={"data": overpass_query},
        headers=headers,
        retries=2,
    )

    results = []
    for item in payload.get("elements", []):
        tags = item.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        item_lat = item.get("lat") or item.get("center", {}).get("lat")
        item_lon = item.get("lon") or item.get("center", {}).get("lon")
        address = _osm_address(tags)
        results.append(
            ProviderResult(
                source="openstreetmap",
                source_id=f"{item.get('type')}/{item.get('id')}",
                name=name,
                address=address,
                phone=tags.get("phone") or tags.get("contact:phone") or "",
                website=tags.get("website") or tags.get("contact:website") or "",
                email=tags.get("email") or tags.get("contact:email") or "",
                category=tags.get("amenity") or tags.get("healthcare") or tags.get("shop") or "",
                latitude=item_lat,
                longitude=item_lon,
                map_url=f"https://www.openstreetmap.org/{item.get('type')}/{item.get('id')}",
                raw_data=item,
            )
        )
    return results


def _overpass_filters(query, business_type):
    text = f"{query} {business_type}".lower()
    if any(word in text for word in ["hospital", "hospitals", "hmo", "clinic", "medical"]):
        return ['["amenity"="hospital"]', '["amenity"="clinic"]', '["healthcare"~"hospital|clinic|doctor"]']
    if any(word in text for word in ["restaurant", "food", "eatery"]):
        return ['["amenity"="restaurant"]', '["amenity"="fast_food"]']
    if any(word in text for word in ["school", "schools"]):
        return ['["amenity"="school"]', '["amenity"="college"]']
    if any(word in text for word in ["hotel", "lodging"]):
        return ['["tourism"="hotel"]', '["tourism"="guest_house"]']
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", text).strip()
    first_term = cleaned.split()[0] if cleaned else "business"
    return [f'["name"~"{re.escape(first_term)}",i]']


def _osm_address(tags):
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:suburb"),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:country"),
    ]
    return ", ".join(part for part in parts if part)


def build_dedupe_key(result):
    if result.source == "google_places" and result.source_id:
        return f"google:{result.source_id}".lower()
    website = normalize_domain(result.website)
    if website:
        return f"website:{website}"
    name = re.sub(r"[^a-z0-9]+", "", (result.name or "").lower())
    address = re.sub(r"[^a-z0-9]+", "", (result.address or "").lower())
    phone = re.sub(r"[^0-9]+", "", result.phone or "")
    return f"business:{name}:{phone or address[:80]}"


def normalize_domain(value):
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.lower().removeprefix("www.")


def enrich_from_website(lead):
    if not lead.website:
        return lead
    try:
        response = requests.get(
            lead.website,
            headers={"User-Agent": "BusinessDirectoryScraper/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return lead

    text = response.text[:250000]
    emails = [email for email in sorted(set(EMAIL_RE.findall(text))) if not email.lower().endswith((".png", ".jpg"))]
    socials = {}
    for key, pattern in SOCIAL_PATTERNS.items():
        found = pattern.findall(text)
        if found:
            socials[key] = sorted(set(found))[:3]

    if emails and not lead.email:
        lead.email = emails[0]
    if socials:
        lead.socials = {**(lead.socials or {}), **socials}
    lead.save(update_fields=["email", "socials", "updated_at"])
    return lead


def score_lead(result, search_text):
    text = " ".join(
        str(value or "") for value in [result.name, result.address, result.category, result.website, result.email, search_text]
    ).lower()
    score = 20
    tags = []
    if result.phone:
        score += 15
        tags.append("Has phone")
    if not result.website:
        score += 25
        tags.append("No website")
    else:
        score += 10
        tags.append("Has website")
    if result.email:
        score += 15
        tags.append("Has email")
    if result.rating and result.review_count:
        score += min(20, int(result.review_count / 10))
        tags.append("Reviewed")
    if "hmo" in text:
        score += 20
        tags.append("HMO signal")
    return min(score, 100), tags


EXPORT_COLUMNS = [
    "name",
    "category",
    "address",
    "phone",
    "email",
    "website",
    "rating",
    "review_count",
    "lead_score",
    "duplicate_count",
    "map_url",
    "latitude",
    "longitude",
]


def leads_to_rows(leads):
    rows = []
    for lead in leads:
        rows.append(
            {
                "name": lead.name,
                "category": lead.category,
                "address": lead.address,
                "phone": lead.phone,
                "email": lead.email,
                "website": lead.website,
                "rating": lead.rating,
                "review_count": lead.review_count,
                "lead_score": lead.lead_score,
                "duplicate_count": lead.duplicate_count,
                "map_url": lead.map_url,
                "latitude": lead.latitude,
                "longitude": lead.longitude,
            }
        )
    return rows


def rows_to_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def rows_to_xlsx(rows):
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("Install openpyxl to export XLSX files.") from exc

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Leads"
    worksheet.append(EXPORT_COLUMNS)
    for row in rows:
        worksheet.append([row.get(column, "") for column in EXPORT_COLUMNS])
    for column_cells in worksheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 45)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def rows_to_json(rows):
    return json.dumps(rows, indent=2, default=str)


def normalize_filename(value):
    parsed = urlparse(value)
    value = parsed.netloc or value
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "leads"
