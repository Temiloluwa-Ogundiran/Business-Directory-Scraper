from concurrent.futures import ThreadPoolExecutor, as_completed

from django.contrib import messages
from django.conf import settings
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import BusinessSearchForm, LeadFilterForm
from .models import ExportRecord, Lead, SearchCampaign
from .services import (
    build_dedupe_key,
    build_search_phrase,
    enrich_google_place_details_bulk,
    google_places_search,
    leads_to_rows,
    normalize_filename,
    plan_search_queries_with_llm,
    ProviderResult,
    rows_to_csv,
    rows_to_json,
    rows_to_xlsx,
    score_lead,
)


def search_business(request):
    if request.method == "POST":
        form = BusinessSearchForm(request.POST)
        if form.is_valid():
            campaign = _run_campaign(form.cleaned_data)
            if campaign.status == "failed":
                messages.error(request, campaign.error_message)
            else:
                messages.success(request, f"Found {campaign.total_found} leads for {campaign}.")
            return redirect("campaign_detail", campaign_id=campaign.id)
    else:
        form = BusinessSearchForm()

    campaigns = SearchCampaign.objects.all()[:10]
    return render(request, "finder/search.html", {"form": form, "campaigns": campaigns})


def campaign_detail(request, campaign_id):
    campaign = get_object_or_404(SearchCampaign, id=campaign_id)
    filter_form = LeadFilterForm(request.GET or None)
    leads = campaign.leads.all()

    if filter_form.is_valid():
        data = filter_form.cleaned_data
        if data.get("q"):
            term = data["q"]
            leads = leads.filter(
                Q(name__icontains=term)
                | Q(address__icontains=term)
                | Q(category__icontains=term)
                | Q(tags__icontains=term)
            )
        if data.get("missing_website"):
            leads = leads.filter(Q(website="") | Q(website__isnull=True))
        if data.get("has_phone"):
            leads = leads.exclude(phone="")
        if data.get("has_email"):
            leads = leads.exclude(email="")
        if data.get("duplicates"):
            leads = leads.filter(duplicate_count__gt=0)

    return render(
        request,
        "finder/search.html",
        {
            "form": BusinessSearchForm(),
            "campaigns": SearchCampaign.objects.all()[:10],
            "campaign": campaign,
            "filter_form": filter_form,
            "leads": leads,
            "fetched_variant_count": int((campaign.search_plan or {}).get("fetched_variant_count", 0) or 0),
            "total_variant_count": len((campaign.search_plan or {}).get("query_variants", [])),
            "has_more_results": int((campaign.search_plan or {}).get("fetched_variant_count", 0) or 0)
            < len((campaign.search_plan or {}).get("query_variants", [])),
        },
    )


def export_leads(request, campaign_id, export_format):
    campaign = get_object_or_404(SearchCampaign, id=campaign_id)
    leads = campaign.leads.all()
    selected_ids = request.POST.getlist("selected_leads")
    if selected_ids:
        leads = leads.filter(id__in=selected_ids)
    rows = leads_to_rows(leads)
    filename = normalize_filename(str(campaign))

    if export_format == "csv":
        ExportRecord.objects.create(campaign=campaign, export_format="csv", row_count=len(rows))
        response = HttpResponse(rows_to_csv(rows), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        return response

    if export_format == "json":
        ExportRecord.objects.create(campaign=campaign, export_format="json", row_count=len(rows))
        response = HttpResponse(rows_to_json(rows), content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{filename}.json"'
        return response

    if export_format == "xlsx":
        try:
            payload = rows_to_xlsx(rows)
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("campaign_detail", campaign_id=campaign.id)
        ExportRecord.objects.create(campaign=campaign, export_format="xlsx", row_count=len(rows))
        response = HttpResponse(
            payload,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response

    messages.error(request, "Unsupported export request.")
    return redirect(reverse("campaign_detail", kwargs={"campaign_id": campaign.id}))


def load_next_results(request, campaign_id):
    campaign = get_object_or_404(SearchCampaign, id=campaign_id)
    if request.method != "POST":
        return redirect("campaign_detail", campaign_id=campaign.id)

    search_plan = campaign.search_plan or {}
    variants = search_plan.get("query_variants", [])
    fetched_count = int(search_plan.get("fetched_variant_count", 0) or 0)
    batch_size = int(search_plan.get("batch_size", getattr(settings, "SEARCH_VARIANT_BATCH_SIZE", 5)) or 5)

    if fetched_count >= len(variants):
        messages.info(request, "No more planned result batches for this search.")
        return redirect("campaign_detail", campaign_id=campaign.id)

    next_variants = variants[fetched_count:fetched_count + batch_size]
    data = {
        "query": campaign.query,
        "location": campaign.location,
        "business_type": campaign.business_type,
        "google_pages": search_plan.get("google_pages", 1),
    }

    try:
        provider_results = _run_google_variants(next_variants, data)
        created_count = _save_provider_results(campaign, provider_results, variants, search_plan)
        search_plan["fetched_variant_count"] = fetched_count + len(next_variants)
        campaign.search_plan = search_plan
        campaign.total_found = campaign.leads.count()
        campaign.source_counts = dict(campaign.leads.values_list("source").annotate(total=Count("id")))
        campaign.status = "completed"
        campaign.error_message = ""
        campaign.save(update_fields=["search_plan", "total_found", "source_counts", "status", "error_message", "updated_at"])
        messages.success(request, f"Loaded {created_count} additional leads.")
    except Exception as exc:
        messages.error(request, str(exc))

    return redirect("campaign_detail", campaign_id=campaign.id)


def enrich_campaign_contacts(request, campaign_id):
    campaign = get_object_or_404(SearchCampaign, id=campaign_id)
    if request.method != "POST":
        return redirect("campaign_detail", campaign_id=campaign.id)

    leads = list(
        campaign.leads.filter(source="google_places")
        .filter(Q(phone="") | Q(website=""))
        .exclude(source_id="")
    )
    provider_results = [
        _lead_to_provider_result(lead)
        for lead in leads
    ]

    try:
        enrich_google_place_details_bulk(provider_results)
        updated_count = _save_enriched_contacts(leads, provider_results)
        messages.success(request, f"Updated contact details for {updated_count} leads.")
    except Exception as exc:
        messages.error(request, str(exc))

    return redirect("campaign_detail", campaign_id=campaign.id)


def _run_campaign(data):
    sources = ["google_places"]

    campaign = SearchCampaign.objects.create(
        query=data["query"],
        location=data.get("location", ""),
        business_type=data.get("business_type", ""),
        sources=sources,
        llm_enabled=True,
    )

    try:
        max_variants = min(data.get("llm_variants") or 1, getattr(settings, "OPENAI_SEARCH_VARIANTS", 5))
        search_plan = plan_search_queries_with_llm(
            data["query"],
            location=data.get("location", ""),
            business_type=data.get("business_type", ""),
            max_variants=max_variants,
        )
        variants = search_plan.get("query_variants", [])
        batch_size = max(1, min(len(variants) or 1, getattr(settings, "SEARCH_VARIANT_BATCH_SIZE", 5)))
        first_variants = variants[:batch_size]
        search_plan["fetched_variant_count"] = len(first_variants)
        search_plan["batch_size"] = batch_size
        search_plan["google_pages"] = data.get("google_pages") or 1
        campaign.search_plan = search_plan
        campaign.save(update_fields=["search_plan", "updated_at"])

        provider_results = _run_google_variants(first_variants, data)
        _save_provider_results(campaign, provider_results, variants, search_plan)

        campaign.total_found = campaign.leads.count()
        campaign.source_counts = dict(campaign.leads.values_list("source").annotate(total=Count("id")))
        campaign.status = "completed"
    except Exception as exc:
        campaign.status = "failed"
        campaign.error_message = str(exc)

    campaign.save(update_fields=["total_found", "source_counts", "status", "error_message", "updated_at"])
    return campaign


def _save_provider_results(campaign, provider_results, variants, search_plan):
    search_text = " ".join(
        build_search_phrase(
            variant.get("query", ""),
            variant.get("location", ""),
            variant.get("business_type", ""),
        )
        for variant in variants
    )
    planner_signals = [str(signal).strip() for signal in search_plan.get("signals", []) if str(signal).strip()]
    saved_count = 0

    for result in provider_results:
        dedupe_key = build_dedupe_key(result)
        duplicate_count = Lead.objects.filter(dedupe_key=dedupe_key).exclude(campaign=campaign).count()
        previous = Lead.objects.filter(dedupe_key=dedupe_key).exclude(campaign=campaign).order_by("-updated_at").first()
        if previous:
            result.phone = result.phone or previous.phone
            result.website = result.website or previous.website
            result.email = result.email or previous.email
        score, tags = score_lead(result, search_text)
        tags.append("AI planned")
        for signal in planner_signals:
            if signal.lower() in " ".join([result.name, result.address, result.category, search_text]).lower():
                tags.append(signal)
        if duplicate_count:
            tags.append("Seen before")
        tags = list(dict.fromkeys(tags))
        _, created = Lead.objects.update_or_create(
            campaign=campaign,
            source=result.source,
            source_id=result.source_id,
            defaults={
                "name": result.name[:255],
                "address": result.address,
                "phone": result.phone,
                "website": result.website,
                "email": result.email,
                "category": result.category,
                "rating": result.rating,
                "review_count": result.review_count or 0,
                "latitude": result.latitude,
                "longitude": result.longitude,
                "map_url": result.map_url,
                "dedupe_key": dedupe_key,
                "duplicate_count": duplicate_count,
                "has_hmo_signal": "HMO signal" in tags,
                "lead_score": score,
                "tags": tags,
                "raw_data": result.raw_data or {},
            },
        )
        if created:
            saved_count += 1

    return saved_count


def _run_google_variants(variants, data):
    if not variants:
        return []

    max_workers = max(1, min(len(variants), getattr(settings, "GOOGLE_SEARCH_WORKERS", 8)))
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                google_places_search,
                variant.get("query", data["query"]),
                location=variant.get("location", data.get("location", "")),
                business_type=variant.get("business_type", data.get("business_type", "")),
                pages=data.get("google_pages") or 1,
            )
            for variant in variants
        ]
        for future in as_completed(futures):
            results.extend(future.result())
    return enrich_google_place_details_bulk(results)


def _lead_to_provider_result(lead):
    return ProviderResult(
        source=lead.source,
        source_id=lead.source_id,
        name=lead.name,
        address=lead.address,
        phone=lead.phone,
        website=lead.website,
        email=lead.email,
        category=lead.category,
        rating=lead.rating,
        review_count=lead.review_count,
        latitude=lead.latitude,
        longitude=lead.longitude,
        map_url=lead.map_url,
        raw_data=lead.raw_data or {},
    )


def _save_enriched_contacts(leads, provider_results):
    updated_count = 0
    by_id = {result.source_id: result for result in provider_results}
    for lead in leads:
        result = by_id.get(lead.source_id)
        if not result:
            continue
        update_fields = []
        if result.phone and result.phone != lead.phone:
            lead.phone = result.phone
            update_fields.append("phone")
        if result.website and result.website != lead.website:
            lead.website = result.website
            update_fields.append("website")
        if result.map_url and result.map_url != lead.map_url:
            lead.map_url = result.map_url
            update_fields.append("map_url")
        if result.raw_data and result.raw_data != lead.raw_data:
            lead.raw_data = result.raw_data
            update_fields.append("raw_data")
        if update_fields:
            update_fields.append("updated_at")
            lead.save(update_fields=update_fields)
            updated_count += 1
    return updated_count
