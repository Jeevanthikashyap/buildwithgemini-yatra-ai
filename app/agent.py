# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request
import uuid

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

MODEL = "gemini-3.6-flash"
IMAGE_MODEL = "gemini-3.1-flash-lite-image"
VIDEO_MODEL = "gemini-omni-flash-preview"

# IMPORTANT: Hardcoded project ID string. Never read from GOOGLE_CLOUD_PROJECT
# or google.auth.default() as Agent Platform returns project number, breaking Firestore.
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-04-8017249fc17a"

# Public Cloud Storage bucket for generated travel postcards and mood boards
GCS_BUCKET_NAME = "yatra-ai-media-8017249fc17a"

# Agent Engine Code Execution Sandbox provisioned from deployment_metadata.json
AGENT_ENGINE_RESOURCE = "projects/384385961523/locations/us-east1/reasoningEngines/6669529781949693952"
SANDBOX_RESOURCE_NAME = "projects/384385961523/locations/us-east1/reasoningEngines/6669529781949693952/sandboxEnvironments/7992983341001342976"

# Memory Bank (reusing the deployed Agent Engine runtime ID)
MEMORY_BANK_ID = "6669529781949693952"

_firestore_client = None
_storage_client = None
_genai_client = None


def get_storage_client() -> storage.Client:
    """Returns a singleton Storage client."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    return _storage_client


def get_genai_client() -> genai.Client:
    """Returns a singleton GenAI client configured for global Vertex AI."""
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )
    return _genai_client


def get_firestore_client() -> firestore.Client:
    """Returns a singleton Firestore client explicitly initialized with the project ID."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=FIRESTORE_PROJECT_ID)
    return _firestore_client


def search_curated_spots(
    destination: Optional[str] = None,
    category: Optional[str] = None,
    dietary_keyword: Optional[str] = None,
    vibe: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for curated hidden gems, scenic trails, heritage sites, and cafes in Firestore.

    Args:
        destination: Destination name to filter by (e.g., 'Hampi', 'Varanasi', 'Munnar').
        category: Category of spot ('scenic_trail', 'cafe', 'heritage_site', 'experience').
        dietary_keyword: Dietary preference to filter by (e.g., 'vegetarian', 'vegan', 'jain').
        vibe: Desired vibe (e.g., 'scenic', 'heritage', 'chill', 'spiritual').

    Returns:
        List of matching curated spots with descriptions, cost, duration, and dietary options.
    """
    db = get_firestore_client()
    query = db.collection("curated_spots")

    if destination:
        # Title case match
        query = query.where("destination", "==", destination.strip().title())
    if category:
        query = query.where("category", "==", category.strip().lower())

    results = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id

        # In-memory filter for tags / dietary / vibes if requested
        if dietary_keyword:
            kw = dietary_keyword.lower()
            dietary_opts = " ".join(data.get("dietary_options", [])).lower()
            if kw not in dietary_opts:
                continue

        if vibe:
            v_kw = vibe.lower()
            vibes = [v.lower() for v in data.get("vibe", [])]
            if not any(v_kw in v for v in vibes):
                continue

        results.append(data)

    return results


def save_user_itinerary_item(
    destination: str,
    title: str,
    day_number: int,
    start_time: str,
    estimated_cost_inr: float,
    notes: str,
    category: str = "activity",
) -> Dict[str, Any]:
    """Save an approved itinerary item or booked activity to Firestore.

    Args:
        destination: City or destination of the trip (e.g., 'Hampi').
        title: Title of the activity or spot (e.g., 'Matanga Hill Sunrise Trek').
        day_number: Day of the itinerary (e.g. 1, 2, 3).
        start_time: Planned time (e.g. '06:00 AM').
        estimated_cost_inr: Estimated cost in Indian Rupees (INR).
        notes: Dietary notes, booking reference, or travel tips.
        category: 'activity', 'transit', 'meal', 'stay'.

    Returns:
        Confirmation dictionary with the generated item ID.
    """
    db = get_firestore_client()
    item_id = f"itin-{uuid.uuid4().hex[:8]}"
    item_data = {
        "id": item_id,
        "destination": destination.strip().title(),
        "title": title,
        "day_number": day_number,
        "start_time": start_time,
        "estimated_cost_inr": estimated_cost_inr,
        "notes": notes,
        "category": category,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection("itinerary_items").document(item_id).set(item_data)
    return {"status": "success", "message": f"Saved itinerary item '{title}'", "item": item_data}


def get_user_itinerary(destination: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve saved itinerary items for the user from Firestore.

    Args:
        destination: Optional destination filter (e.g. 'Hampi').

    Returns:
        List of saved itinerary items sorted by day and time.
    """
    db = get_firestore_client()
    query = db.collection("itinerary_items")
    if destination:
        query = query.where("destination", "==", destination.strip().title())

    items = [doc.to_dict() for doc in query.stream()]
    items.sort(key=lambda x: (x.get("day_number", 1), x.get("start_time", "")))
    return items


def search_multimodal_transit(
    origin: str,
    destination: str,
    travel_mode: Optional[str] = None,
    max_budget_inr: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Search multi-modal transit options (trains, sleeper buses, cabs, flights) between Indian cities.

    Args:
        origin: Departure city or hub (e.g., 'Bangalore', 'Delhi', 'Kochi', 'Hyderabad').
        destination: Arrival city (e.g., 'Hampi', 'Hosapete', 'Varanasi', 'Munnar').
        travel_mode: Optional mode filter: 'train', 'bus', 'flight', 'cab'.
        max_budget_inr: Maximum acceptable price in INR (₹).

    Returns:
        List of matching transit options with departure/arrival times, duration, operator, class, and price.
    """
    sample_routes = [
        # Bangalore -> Hampi
        {
            "id": "trn-16592",
            "origin": "Bangalore",
            "destination": "Hampi",
            "mode": "train",
            "operator": "Indian Railways (Hampi Express - 16592)",
            "departure_time": "10:00 PM (SBC)",
            "arrival_time": "07:10 AM (HPT - Hosapete)",
            "duration": "9h 10m",
            "travel_class": "3A AC Tier",
            "price_inr": 890,
            "availability": "Available (32 seats)",
            "notes": "Overnight train directly to Hosapete junction; 25 min auto-rickshaw to Hampi ruins.",
            "booking_url": "https://www.irctc.co.in/nget/train-search",
        },
        {
            "id": "bus-ksrtc-airavat",
            "origin": "Bangalore",
            "destination": "Hampi",
            "mode": "bus",
            "operator": "KSRTC Airavat Club Class Multi-Axle",
            "departure_time": "11:00 PM (Majestic)",
            "arrival_time": "06:30 AM (Hampi Bazaar)",
            "duration": "7h 30m",
            "travel_class": "AC Sleeper",
            "price_inr": 1150,
            "availability": "Available (14 berths)",
            "notes": "Direct drop at Hampi Bazaar near Virupaksha temple.",
            "booking_url": "https://ksrtc.in/oprs-web/",
        },
        {
            "id": "cab-intercity-hampi",
            "origin": "Bangalore",
            "destination": "Hampi",
            "mode": "cab",
            "operator": "MakeMyTrip / Savaari Intercity",
            "departure_time": "Flexible (On-demand)",
            "arrival_time": "+6h 30m",
            "duration": "6h 30m",
            "travel_class": "Sedan (AC Dzire/Etios)",
            "price_inr": 6200,
            "availability": "Instant Confirmation",
            "notes": "Door-to-door scenic drive via NH48 & NH50 with toll inclusion.",
            "booking_url": "https://www.makemytrip.com/cabs/",
        },
        # Delhi -> Varanasi
        {
            "id": "trn-22436",
            "origin": "Delhi",
            "destination": "Varanasi",
            "mode": "train",
            "operator": "Indian Railways (Vande Bharat Express - 22436)",
            "departure_time": "06:00 AM (NDLS)",
            "arrival_time": "02:00 PM (BSB)",
            "duration": "8h 00m",
            "travel_class": "Chair Car (CC)",
            "price_inr": 1750,
            "availability": "Available (48 seats)",
            "notes": "Fastest daytime express with morning tea, breakfast, and lunch included.",
            "booking_url": "https://www.irctc.co.in/nget/train-search",
        },
        {
            "id": "flt-6e-2142",
            "origin": "Delhi",
            "destination": "Varanasi",
            "mode": "flight",
            "operator": "IndiGo (6E-2142)",
            "departure_time": "10:45 AM (DEL T2)",
            "arrival_time": "12:15 PM (VNS)",
            "duration": "1h 30m",
            "travel_class": "Economy",
            "price_inr": 3850,
            "availability": "Available",
            "notes": "Quick non-stop flight to Lal Bahadur Shastri Airport; 45m prepaid taxi to Ghats.",
            "booking_url": "https://www.goindigo.in/flight-booking.html",
        },
        # Kochi -> Munnar
        {
            "id": "bus-ksrtc-munnar",
            "origin": "Kochi",
            "destination": "Munnar",
            "mode": "bus",
            "operator": "KSRTC Fast Passenger / Minibus",
            "departure_time": "07:30 AM (Aluva)",
            "arrival_time": "11:45 AM (Munnar Town)",
            "duration": "4h 15m",
            "travel_class": "Semi-Deluxe",
            "price_inr": 180,
            "availability": "Walk-in / Online",
            "notes": "Scenic mountain climb through Cheeyappara waterfalls and tea gardens.",
            "booking_url": "https://www.onlineksrtcswift.com/",
        },
    ]

    orig_clean = origin.strip().lower()
    dest_clean = destination.strip().lower()

    matches = []
    for route in sample_routes:
        if orig_clean not in route["origin"].lower():
            continue
        if dest_clean not in route["destination"].lower() and dest_clean not in route["notes"].lower():
            continue
        if travel_mode and travel_mode.strip().lower() != route["mode"].lower():
            continue
        if max_budget_inr is not None and route["price_inr"] > max_budget_inr:
            continue
        matches.append(route)

    return matches


def search_flights(
    origin: str,
    destination: str,
    departure_date: Optional[str] = None,
    return_date: Optional[str] = None,
    cabin_class: str = "economy",
    max_budget_inr: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Search domestic and international flights with pricing, airlines, stops, and price trends.

    Args:
        origin: Departure city or airport code (e.g., 'Bangalore', 'BLR', 'Delhi', 'DEL', 'Mumbai', 'BOM').
        destination: Arrival city or airport code (e.g., 'Singapore', 'SIN', 'Dubai', 'DXB', 'London', 'LHR', 'Tokyo', 'HND', 'Bangkok', 'BKK', 'Paris', 'CDG', 'Goa', 'GOI').
        departure_date: Desired departure date (e.g. '2026-11-10').
        return_date: Optional return date for round trips.
        cabin_class: 'economy', 'premium_economy', or 'business'.
        max_budget_inr: Maximum budget in INR (₹).

    Returns:
        List of matching flights with airline, flight number, duration, stops, price in INR, and price trend tags.
    """
    flight_catalog = [
        # International routes from Bangalore (BLR)
        {
            "id": "flt-sq509",
            "airline": "Singapore Airlines",
            "flight_number": "SQ 509",
            "origin": "Bangalore (BLR)",
            "destination": "Singapore (SIN)",
            "type": "international",
            "departure_time": "11:15 PM",
            "arrival_time": "06:10 AM (+1 day)",
            "duration": "4h 25m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 18500,
            "baggage": "25kg check-in + 7kg cabin",
            "price_trend": "🔥 Lowest in 30 days (14% below average)",
            "meal_included": True,
            "dietary_options": ["Hindu Vegetarian (AVML)", "Jain Meal (VJML)", "Vegan"],
            "booking_url": "https://www.singaporeair.com/en_UK/in/home#/book/bookflight",
        },
        {
            "id": "flt-6e1005",
            "airline": "IndiGo International",
            "flight_number": "6E 1005",
            "origin": "Bangalore (BLR)",
            "destination": "Singapore (SIN)",
            "type": "international",
            "departure_time": "09:40 AM",
            "arrival_time": "04:45 PM",
            "duration": "4h 35m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 13900,
            "baggage": "20kg check-in + 7kg cabin",
            "price_trend": "📉 Recent price drop (Save ₹2,100)",
            "meal_included": False,
            "dietary_options": ["Pre-book Vegetarian Sandwich/Biryani"],
            "booking_url": "https://www.goindigo.in/flight-booking.html",
        },
        {
            "id": "flt-ek565",
            "airline": "Emirates",
            "flight_number": "EK 565",
            "origin": "Bangalore (BLR)",
            "destination": "Dubai (DXB)",
            "type": "international",
            "departure_time": "10:30 AM",
            "arrival_time": "01:00 PM",
            "duration": "4h 00m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 21800,
            "baggage": "30kg check-in + 7kg cabin",
            "price_trend": "⚡ Stable fare (Good availability)",
            "meal_included": True,
            "dietary_options": ["Vegetarian Jain", "Indian Veg", "Halal"],
            "booking_url": "https://www.emirates.com/in/english/book/",
        },
        {
            "id": "flt-fz408",
            "airline": "Flydubai",
            "flight_number": "FZ 408",
            "origin": "Bangalore (BLR)",
            "destination": "Dubai (DXB)",
            "type": "international",
            "departure_time": "02:15 AM",
            "arrival_time": "04:55 AM",
            "duration": "4h 10m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 15400,
            "baggage": "20kg check-in + 7kg cabin",
            "price_trend": "📉 Budget Pick (Cheapest non-stop to Dubai)",
            "meal_included": False,
            "dietary_options": ["Snack purchase on board"],
            "booking_url": "https://www.flydubai.com/en/",
        },
        {
            "id": "flt-tg326",
            "airline": "Thai Airways",
            "flight_number": "TG 326",
            "origin": "Bangalore (BLR)",
            "destination": "Bangkok (BKK)",
            "type": "international",
            "departure_time": "12:30 AM",
            "arrival_time": "06:00 AM",
            "duration": "4h 00m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 16200,
            "baggage": "25kg check-in + 7kg cabin",
            "price_trend": "🔥 Popular seasonal route",
            "meal_included": True,
            "dietary_options": ["Asian Veg", "Indian Veg", "Jain Meal"],
            "booking_url": "https://www.thaiairways.com/",
        },
        {
            "id": "flt-ba118",
            "airline": "British Airways",
            "flight_number": "BA 118",
            "origin": "Bangalore (BLR)",
            "destination": "London (LHR)",
            "type": "international",
            "departure_time": "07:00 AM",
            "arrival_time": "01:15 PM",
            "duration": "10h 45m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 48500,
            "baggage": "23kg check-in + 7kg cabin",
            "price_trend": "⚡ Fares rising (Book soon)",
            "meal_included": True,
            "dietary_options": ["Asian Vegetarian (AVML)", "Jain", "Vegan"],
            "booking_url": "https://www.britishairways.com/travel/home/public/en_in/",
        },
        # Delhi (DEL) Routes
        {
            "id": "flt-ai187",
            "airline": "Air India",
            "flight_number": "AI 187",
            "origin": "Delhi (DEL)",
            "destination": "London (LHR)",
            "type": "international",
            "departure_time": "02:45 AM",
            "arrival_time": "07:30 AM",
            "duration": "9h 15m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 43200,
            "baggage": "2x23kg check-in + 7kg cabin",
            "price_trend": "📉 High baggage allowance special",
            "meal_included": True,
            "dietary_options": ["Authentic Indian Vegetarian", "Jain", "Halal"],
            "booking_url": "https://www.airindia.com/",
        },
        {
            "id": "flt-nh838",
            "airline": "All Nippon Airways (ANA)",
            "flight_number": "NH 838",
            "origin": "Delhi (DEL)",
            "destination": "Tokyo (HND)",
            "type": "international",
            "departure_time": "06:20 PM",
            "arrival_time": "05:40 AM (+1 day)",
            "duration": "7h 50m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 49900,
            "baggage": "2x23kg check-in + 7kg cabin",
            "price_trend": "🔥 Top rated 5-star service",
            "meal_included": True,
            "dietary_options": ["Vegetarian Oriental", "Indian Veg", "Jain"],
            "booking_url": "https://www.ana.co.jp/en/in/",
        },
        # Domestic flight picks
        {
            "id": "flt-6e412",
            "airline": "IndiGo",
            "flight_number": "6E 412",
            "origin": "Bangalore (BLR)",
            "destination": "Goa (GOI)",
            "type": "domestic",
            "departure_time": "08:15 AM",
            "arrival_time": "09:30 AM",
            "duration": "1h 15m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 3200,
            "baggage": "15kg check-in + 7kg cabin",
            "price_trend": "📉 Price drop: ₹950 cheaper than weekend average",
            "meal_included": False,
            "dietary_options": ["Buy on board"],
            "booking_url": "https://www.goindigo.in/",
        },
        {
            "id": "flt-ai804",
            "airline": "Air India",
            "flight_number": "AI 804",
            "origin": "Delhi (DEL)",
            "destination": "Varanasi (VNS)",
            "type": "domestic",
            "departure_time": "10:15 AM",
            "arrival_time": "11:40 AM",
            "duration": "1h 25m",
            "stops": "Non-stop",
            "cabin_class": "economy",
            "price_inr": 3800,
            "baggage": "15kg check-in + 7kg cabin",
            "price_trend": "⚡ Stable fare",
            "meal_included": True,
            "dietary_options": ["Hot Vegetarian snack box"],
            "booking_url": "https://www.airindia.com/",
        },
    ]

    orig_clean = origin.strip().lower()
    dest_clean = destination.strip().lower()

    matches = []
    for flt in flight_catalog:
        if orig_clean not in flt["origin"].lower() and orig_clean not in flt["flight_number"].lower():
            continue
        if dest_clean not in flt["destination"].lower():
            continue
        if cabin_class and cabin_class.lower() != flt["cabin_class"].lower():
            continue
        if max_budget_inr is not None and flt["price_inr"] > max_budget_inr:
            continue
        matches.append(flt)

    # If no exact city code match found, return available routes matching the destination or helpful alternates
    if not matches:
        for flt in flight_catalog:
            if dest_clean in flt["destination"].lower():
                matches.append(flt)

    return matches


def search_hotels(
    destination: str,
    check_in_date: Optional[str] = None,
    check_out_date: Optional[str] = None,
    guests: int = 1,
    max_price_per_night_inr: Optional[float] = None,
    vibe: Optional[str] = None,
    dietary_needs: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search domestic and international hotels with rates, ratings, amenities, and dietary suitability.

    Args:
        destination: City or destination (e.g. 'Singapore', 'Dubai', 'Bangkok', 'London', 'Hampi', 'Goa', 'Munnar', 'Varanasi').
        check_in_date: Check-in date (e.g. '2026-11-10').
        check_out_date: Check-out date.
        guests: Number of guests (default 1).
        max_price_per_night_inr: Maximum price per night in INR (₹).
        vibe: Preferred vibe: 'heritage', 'luxury', 'boutique', 'budget', 'scenic'.
        dietary_needs: Specific dietary preferences: 'pure_veg', 'jain', 'halal', 'vegan'.

    Returns:
        List of matching hotels with nightly rates, location, amenities, and rating.
    """
    hotel_catalog = [
        # Singapore
        {
            "id": "htl-sin-mbs",
            "name": "Marina Bay Sands Luxury Resort",
            "destination": "Singapore",
            "stars": 5,
            "rating": 4.8,
            "neighborhood": "Marina Bay",
            "price_per_night_inr": 42000,
            "amenities": ["Infinity pool", "Rooftop SkyPark", "Spa", "Free high-speed WiFi", "Direct Metro Access"],
            "dietary_notes": "Multiple Michelin-rated restaurants with Jain & pure vegetarian menus available.",
            "vibe": "luxury",
        },
        {
            "id": "htl-sin-clarke",
            "name": "Holiday Inn Express Singapore Clarke Quay",
            "destination": "Singapore",
            "stars": 4,
            "rating": 4.5,
            "neighborhood": "Clarke Quay / Riverside",
            "price_per_night_inr": 11500,
            "amenities": ["Rooftop pool", "Free Express breakfast", "Fitness center", "Close to Little India food options"],
            "dietary_notes": "Fresh vegetarian breakfast buffet; 10 min to Saravanaa Bhavan Little India.",
            "vibe": "boutique",
        },
        # Dubai
        {
            "id": "htl-dxb-marina",
            "name": "Rove Dubai Marina",
            "destination": "Dubai",
            "stars": 4,
            "rating": 4.7,
            "neighborhood": "Dubai Marina",
            "price_per_night_inr": 7800,
            "amenities": ["Outdoor pool", "Free WiFi", "24/7 gym", "Beach shuttle", "Modern co-working spaces"],
            "dietary_notes": "100% Halal certified dining with dedicated Indian vegetarian menu options.",
            "vibe": "budget",
        },
        {
            "id": "htl-dxb-atlantis",
            "name": "Atlantis, The Palm",
            "destination": "Dubai",
            "stars": 5,
            "rating": 4.9,
            "neighborhood": "Palm Jumeirah",
            "price_per_night_inr": 38500,
            "amenities": ["Private beach", "Aquaventure waterpark access", "Underwater aquarium", "World-class spa"],
            "dietary_notes": "Fine dining with custom Jain and pure vegetarian course options upon request.",
            "vibe": "luxury",
        },
        # Bangkok
        {
            "id": "htl-bkk-amari",
            "name": "Amari Watergate Bangkok",
            "destination": "Bangkok",
            "stars": 5,
            "rating": 4.6,
            "neighborhood": "Pratunam",
            "price_per_night_inr": 8200,
            "amenities": ["Breeze Spa", "Outdoor pool", "Fitness club", "Next to CentralWorld shopping"],
            "dietary_notes": "Special Indian breakfast station with fresh dosas, poha, and vegetarian thalis.",
            "vibe": "luxury",
        },
        # London
        {
            "id": "htl-lon-stjames",
            "name": "St. James' Court, A Taj Hotel",
            "destination": "London",
            "stars": 5,
            "rating": 4.8,
            "neighborhood": "Westminster / Buckingham Palace",
            "price_per_night_inr": 28000,
            "amenities": ["Courtyard garden", "Michelin-starred Quilon restaurant", "Jiva Spa", "Historic Victorian heritage"],
            "dietary_notes": "Pioneering Indian coastal and pure vegetarian fine dining (Taj hospitality).",
            "vibe": "heritage",
        },
        # India (Hampi, Munnar, Varanasi)
        {
            "id": "htl-hmp-ktdc",
            "name": "KSTDC Hotel Mayura Bhuvaneshwari Hampi",
            "destination": "Hampi",
            "stars": 3,
            "rating": 4.3,
            "neighborhood": "Kamalapur (Heritage Zone)",
            "price_per_night_inr": 2900,
            "amenities": ["Garden", "Restaurant", "Parking", "5 min auto-rickshaw to Queen's Bath"],
            "dietary_notes": "Pure South Indian vegetarian breakfast and simple home-style meals.",
            "vibe": "heritage",
        },
        {
            "id": "htl-hmp-evolve",
            "name": "Evolve Back, Kamalapura Palace Hampi",
            "destination": "Hampi",
            "stars": 5,
            "rating": 4.9,
            "neighborhood": "Kamalapura",
            "price_per_night_inr": 24000,
            "amenities": ["Vijayanagara palace architecture", "Private infinity pool", "Ayurvedic wellness", "Reading lounge"],
            "dietary_notes": "Gourmet multicourse dining catering to strict Jain, vegan, and sattvic preferences.",
            "vibe": "luxury",
        },
        {
            "id": "htl-mun-tea",
            "name": "Windermere Estate Tea Plantation Retreat",
            "destination": "Munnar",
            "stars": 4,
            "rating": 4.8,
            "neighborhood": "Pothamedu Viewpoint",
            "price_per_night_inr": 8500,
            "amenities": ["Working tea & cardamom estate", "Misty valley views", "Trekking trails", "Campfire"],
            "dietary_notes": "Farm-to-table organic vegetarian Kerala delicacies.",
            "vibe": "scenic",
        },
        {
            "id": "htl-vns-taj",
            "name": "BrijRama Palace, Varanasi - A Heritage Hotel",
            "destination": "Varanasi",
            "stars": 5,
            "rating": 4.9,
            "neighborhood": "Darbhanga Ghat",
            "price_per_night_inr": 26000,
            "amenities": ["18th-century palace on the Ganges", "Bajra boat rides", "Live classical sitar evenings"],
            "dietary_notes": "Strictly 100% Pure Vegetarian with exquisite Banarasi satvik dining.",
            "vibe": "spiritual",
        },
    ]

    dest_clean = destination.strip().lower()
    matches = []
    for htl in hotel_catalog:
        if dest_clean not in htl["destination"].lower() and dest_clean not in htl["neighborhood"].lower():
            continue
        if max_price_per_night_inr is not None and htl["price_per_night_inr"] > max_price_per_night_inr:
            continue
        if vibe and vibe.lower() not in htl["vibe"].lower():
            continue
        if dietary_needs and dietary_needs.lower() not in htl["dietary_notes"].lower():
            continue
        matches.append(htl)

    if not matches:
        # Fallback to broader destination match
        for htl in hotel_catalog:
            if dest_clean in htl["destination"].lower():
                matches.append(htl)

    return matches


def book_travel_item(
    item_type: str,
    title: str,
    origin: str,
    destination: str,
    start_date: str,
    end_date: Optional[str] = None,
    total_cost_inr: float = 0.0,
    passenger_name: str = "Traveler",
    details: Optional[str] = None,
) -> Dict[str, Any]:
    """Book and confirm a domestic or international flight, train, bus, or hotel reservation and save it to the user's Firestore itinerary.

    Args:
        item_type: 'flight' (domestic or international), 'train', 'bus', 'hotel', or 'activity'.
        title: Title of booking (e.g. 'Singapore Airlines SQ509 BLR->SIN', 'IndiGo 6E 1005', 'KSRTC Airavat Club Class', 'Vande Bharat Express 20608', 'Holiday Inn Clarke Quay').
        origin: Departure point or check-in city.
        destination: Arrival city or hotel location.
        start_date: Travel date or check-in date (YYYY-MM-DD).
        end_date: Optional return or check-out date.
        total_cost_inr: Total confirmed cost in INR (₹).
        passenger_name: Primary passenger / guest name.
        details: Seat numbers, coach/class, baggage allowance, meal preference, or cancellation terms.

    Returns:
        Confirmation details with booking PNR / reference code, status, and saved Firestore document ID.
    """
    prefix_map = {"flight": "FLI", "train": "TRN", "bus": "BUS", "hotel": "HTL", "activity": "ACT"}
    prefix = prefix_map.get(item_type.lower(), item_type[:3].upper())
    pnr_code = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

    booking_record = {
        "id": f"bk-{uuid.uuid4().hex[:8]}",
        "booking_reference": pnr_code,
        "item_type": item_type.lower(),
        "title": title,
        "origin": origin,
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "total_cost_inr": total_cost_inr,
        "passenger_name": passenger_name,
        "details": details or "Instant confirmation issued. Free cancellation up to 48 hours before travel.",
        "status": "CONFIRMED",
        "booked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    # Save to user's itinerary collection in Firestore
    db = get_firestore_client()
    db.collection("itinerary_items").document(booking_record["id"]).set({
        "id": booking_record["id"],
        "destination": destination.strip().title(),
        "title": f"[{item_type.upper()}] {title} (Ref: {pnr_code})",
        "day_number": 1,
        "start_time": start_date,
        "estimated_cost_inr": total_cost_inr,
        "notes": f"PNR: {pnr_code} | Guest: {passenger_name} | {details or ''}",
        "category": item_type.lower(),
        "created_at": booking_record["booked_at"],
    })

    booking_tag = (
        f"\n[CONFIRMED_BOOKING]\n"
        f"Type: {item_type.lower()}\n"
        f"PNR: {pnr_code}\n"
        f"Passenger: {passenger_name}\n"
        f"Title: {title}\n"
        f"From: {origin}\n"
        f"To: {destination}\n"
        f"Date: {start_date}\n"
        f"Amount: {int(total_cost_inr)}\n"
        f"Class: Confirmed\n"
        f"Seat: {details or 'Assigned'}\n"
        f"Status: CONFIRMED\n"
        f"[/CONFIRMED_BOOKING]\n"
    )

    return {
        "status": "success",
        "booking_reference": pnr_code,
        "confirmation_message": f"Successfully confirmed {item_type} booking for {passenger_name}! You can now download your official PDF E-Ticket & Receipt directly.",
        "booking_details": booking_record,
        "e_ticket_tag": booking_tag,
    }


def create_price_drop_alert(
    route_type: str,
    origin: str,
    destination: str,
    current_price_inr: float,
    target_price_inr: Optional[float] = None,
    notify_on_any_drop: bool = True,
) -> Dict[str, Any]:
    """Create a price watch alert for flights or trains to notify the user when fares drop.

    Args:
        route_type: 'flight' or 'train'.
        origin: Departure city/station (e.g. 'Bangalore', 'Delhi', 'BLR').
        destination: Arrival city/station (e.g. 'Singapore', 'London', 'Hosapete', 'Dubai').
        current_price_inr: Current fare observed in INR (₹).
        target_price_inr: Desired threshold price to trigger high-priority alerts.
        notify_on_any_drop: Whether to notify as soon as any fare decrease occurs.

    Returns:
        Confirmation dictionary with the generated Alert ID and watch parameters.
    """
    alert_id = f"alert-{uuid.uuid4().hex[:6]}"
    target = target_price_inr if target_price_inr is not None else (current_price_inr * 0.9)  # default 10% drop target

    alert_data = {
        "alert_id": alert_id,
        "route_type": route_type.lower(),
        "origin": origin.strip(),
        "destination": destination.strip(),
        "current_price_inr": current_price_inr,
        "target_price_inr": target,
        "notify_on_any_drop": notify_on_any_drop,
        "active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    db = get_firestore_client()
    db.collection("price_alerts").document(alert_id).set(alert_data)

    return {
        "status": "active",
        "alert_id": alert_id,
        "message": f"Price drop watch activated for {route_type} from {origin} to {destination}.",
        "baseline_price_inr": current_price_inr,
        "target_alert_threshold_inr": target,
    }


def check_price_drop_alerts() -> List[Dict[str, Any]]:
    """Scan all active price alerts in Firestore, evaluate against real-time price trends, and report detected drops.

    Returns:
        List of triggered price drop notifications with savings amounts and booking advice.
    """
    db = get_firestore_client()
    alerts_ref = db.collection("price_alerts").where("active", "==", True).stream()

    notifications = []
    # Simulated live fare fluctuations based on recent airline & railway yield adjustments
    market_discounts = {
        ("bangalore", "singapore"): {"new_price": 13900, "drop_amount": 4600, "reason": "IndiGo Flash Sale & Singapore Airlines partner fare match"},
        ("bangalore", "dubai"): {"new_price": 14200, "drop_amount": 2300, "reason": "Flydubai mid-week fare concession"},
        ("bangalore", "hampi"): {"new_price": 780, "drop_amount": 110, "reason": "Tatkal quota dynamic pricing softening"},
        ("delhi", "london"): {"new_price": 39800, "drop_amount": 3400, "reason": "Air India autumn special promo"},
        ("bangalore", "goa"): {"new_price": 2499, "drop_amount": 701, "reason": "Monsoon end discount on early morning slots"},
    }

    for doc in alerts_ref:
        alert = doc.to_dict()
        orig = alert.get("origin", "").strip().lower()
        dest = alert.get("destination", "").strip().lower()
        baseline = alert.get("current_price_inr", 0.0)

        # Look up simulated market movements
        match = None
        for (k_orig, k_dest), data in market_discounts.items():
            if (k_orig in orig or orig in k_orig) and (k_dest in dest or dest in k_dest):
                match = data
                break

        if match and match["new_price"] < baseline:
            savings = baseline - match["new_price"]
            percent = round((savings / baseline) * 100, 1)
            notifications.append({
                "alert_id": alert.get("alert_id"),
                "route": f"{alert.get('origin')} ➔ {alert.get('destination')} ({alert.get('route_type').title()})",
                "original_price_inr": baseline,
                "discounted_price_inr": match["new_price"],
                "savings_inr": savings,
                "drop_percentage": f"{percent}%",
                "deal_insight": match["reason"],
                "action": "Recommended to lock in this fare now before seats run out.",
            })
        else:
            # Report monitoring status
            notifications.append({
                "alert_id": alert.get("alert_id"),
                "route": f"{alert.get('origin')} ➔ {alert.get('destination')}",
                "status": "Monitored",
                "current_price_inr": baseline,
                "note": "Fare is currently stable. We will alert you immediately if it dips below your target.",
            })

    return notifications


def get_live_destination_weather(destination: str) -> Dict[str, Any]:
    """Fetch live real-time weather and forecast for any Indian city or travel destination via Open-Meteo.

    Args:
        destination: City or destination name (e.g. 'Hampi', 'Varanasi', 'Munnar', 'Jaipur', 'Goa').

    Returns:
        Dictionary containing current temperature (°C), weather conditions, humidity (%), and travel comfort advice.
    """
    clean_dest = destination.strip()
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(clean_dest)}&count=1&language=en&format=json"

    try:
        req = urllib.request.Request(geo_url, headers={"User-Agent": "YatraAI/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            geo_data = json.loads(response.read().decode())

        results = geo_data.get("results")
        if not results:
            return {"error": f"Could not locate destination '{clean_dest}' for weather lookup."}

        place = results[0]
        lat, lon = place["latitude"], place["longitude"]
        place_name = f"{place.get('name')}, {place.get('admin1', '')} ({place.get('country', 'India')})"

        # Fetch current weather
        forecast_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m&timezone=auto"
        )
        req_forecast = urllib.request.Request(forecast_url, headers={"User-Agent": "YatraAI/1.0"})
        with urllib.request.urlopen(req_forecast, timeout=5) as response:
            weather_data = json.loads(response.read().decode())

        current = weather_data.get("current", {})
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        precip = current.get("precipitation", 0.0)
        wind = current.get("wind_speed_10m")
        w_code = current.get("weather_code", 0)

        # Interpret WMO code
        weather_conditions = "Clear skies"
        if w_code in [1, 2, 3]:
            weather_conditions = "Partly cloudy / overcast"
        elif w_code in [45, 48]:
            weather_conditions = "Foggy / misty"
        elif w_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
            weather_conditions = "Rain showers"
        elif w_code >= 95:
            weather_conditions = "Thunderstorms"

        # Travel guidance
        if temp and temp > 34:
            advice = "Hot afternoon; best to explore monuments early morning or late evening, carry hydration."
        elif precip > 1.0 or "Rain" in weather_conditions:
            advice = "Rain expected; carry an umbrella or rain cover for hiking and camera gear."
        else:
            advice = "Pleasant weather; ideal for walking tours, boulder treks, and outdoor heritage exploration."

        return {
            "destination": place_name,
            "temperature_c": temp,
            "condition": weather_conditions,
            "humidity_percent": humidity,
            "precipitation_mm": precip,
            "wind_speed_kmh": wind,
            "travel_advice": advice,
        }
    except Exception as e:
        return {"error": f"Failed to retrieve weather for {clean_dest}: {str(e)}"}


def geocode_address(address: str) -> Dict[str, Any]:
    """Turn an address or landmark into geographic coordinates using the Google Maps Geocoding API.

    Args:
        address: The street address or landmark to geocode (e.g. 'Virupaksha Temple, Hampi', 'Assi Ghat, Varanasi').

    Returns:
        Dictionary with formatted address, latitude, and longitude.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {
            "error": "GOOGLE_MAPS_API_KEY environment variable is not configured with a valid key."
        }

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address.strip())}&key={api_key}"
    try:
        req = urllib.request.Request(url, headers={"X-Goog-Api-Key": api_key})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        status = data.get("status")
        if status != "OK" or not data.get("results"):
            return {"error": f"Geocoding failed for '{address}': {status}", "details": data.get("error_message")}

        top_result = data["results"][0]
        location = top_result.get("geometry", {}).get("location", {})
        return {
            "name": address,
            "formatted_address": top_result.get("formatted_address"),
            "location": {
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
            },
            "place_id": top_result.get("place_id"),
        }
    except Exception as e:
        return {"error": f"Error calling Geocoding API: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 2000.0,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """Find nearby places of a given type using the Google Maps Places API (New) searchNearby REST endpoint.

    Args:
        latitude: Latitude coordinate for search center.
        longitude: Longitude coordinate for search center.
        place_type: Type of place to search for (e.g., 'tourist_attraction', 'restaurant', 'cafe', 'lodging', 'hindu_temple').
        radius_meters: Search radius in meters (default 2000m / 2km).
        max_results: Maximum number of places to return (default 5).

    Returns:
        List of nearby places with name, address, and location.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return [{
            "error": "GOOGLE_MAPS_API_KEY environment variable is not configured with a valid key."
        }]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.primaryType",
    }
    payload = {
        "includedTypes": [place_type.strip().lower()],
        "maxResultCount": max_results,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        places = data.get("places", [])
        results = []
        for p in places:
            display_name = p.get("displayName", {}).get("text")
            address = p.get("formattedAddress")
            loc = p.get("location", {})
            results.append({
                "name": display_name,
                "address": address,
                "location": {
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                },
                "primary_type": p.get("primaryType"),
            })
        return results
    except Exception as e:
        return [{"error": f"Error calling Places API (New): {str(e)}"}]


async def generate_destination_postcard(
    destination: str,
    scene_description: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """Generate a vibrant travel postcard or mood board image for an Indian destination using gemini-3.1-flash-lite-image in the global region.

    Saves the generated image as an artifact in the Playground Artifacts panel and uploads it directly to Cloud Storage for a public URL.

    Args:
        destination: Name of the destination (e.g. 'Hampi', 'Varanasi', 'Munnar', 'Jaipur').
        scene_description: Detailed visual prompt describing the scene, lighting, mood, and architecture.

    Returns:
        Dictionary with destination, artifact filename, public Cloud Storage image URL, and description.
    """
    client = get_genai_client()
    prompt = (
        f"A breathtaking, artistic, high-resolution travel postcard of {destination}. "
        f"{scene_description}. Rich colors, cultural warmth, cinematic lighting."
    )

    try:
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_part = None
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data:
                    image_part = part
                    break
            if image_part:
                break

        if not image_part or not image_part.inline_data:
            return {"error": "Image model did not return any image data."}

        image_bytes = image_part.inline_data.data
        mime_type = image_part.inline_data.mime_type or "image/jpeg"
        ext = "jpg" if "jpeg" in mime_type else "png"

        # 1. Save with tool_context.save_artifact for Playground Artifacts panel
        safe_dest = destination.lower().replace(" ", "_")
        artifact_filename = f"postcard_{safe_dest}_{uuid.uuid4().hex[:6]}.{ext}"
        await tool_context.save_artifact(
            filename=artifact_filename,
            artifact=types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        )

        # 2. Upload directly to Cloud Storage bucket and return public HTTPS URL
        storage_cli = get_storage_client()
        bucket = storage_cli.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"postcards/{artifact_filename}")
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/postcards/{artifact_filename}"

        return {
            "status": "success",
            "destination": destination,
            "artifact_filename": artifact_filename,
            "public_image_url": public_url,
            "message": f"Generated postcard for {destination}. Saved to Playground Artifacts and Cloud Storage.",
        }
    except Exception as e:
        return {"error": f"Failed to generate postcard image: {str(e)}"}


async def generate_destination_video(
    destination: str,
    scene_description: str,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """Generate a short cinematic video for an Indian travel destination using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the generated video as an artifact in the Playground Artifacts panel and uploads it directly to Cloud Storage for a public URL.

    Args:
        destination: Name of the destination or monument (e.g. 'Hampi', 'Varanasi', 'Munnar', 'Taj Mahal').
        scene_description: Detailed visual prompt describing motion, camera movement, scene atmosphere, lighting, and ambient sound.

    Returns:
        Dictionary with destination, artifact filename, public Cloud Storage video URL, and description.
    """
    client = get_genai_client()
    prompt = (
        f"A cinematic high-quality travel video clip of {destination}. "
        f"{scene_description}. Smooth continuous motion, vivid atmosphere, 4k travel documentary style."
    )

    try:
        interaction = client.interactions.create(
            model=VIDEO_MODEL,
            input=prompt,
        )

        video_bytes = None
        if hasattr(interaction, "output_video") and interaction.output_video:
            raw_data = interaction.output_video.data
            if isinstance(raw_data, str):
                video_bytes = base64.b64decode(raw_data)
            elif isinstance(raw_data, bytes):
                video_bytes = raw_data

        if not video_bytes:
            return {"error": f"Omni model did not return any video bytes: {interaction}"}

        mime_type = "video/mp4"
        safe_dest = destination.lower().replace(" ", "_")
        artifact_filename = f"video_{safe_dest}_{uuid.uuid4().hex[:6]}.mp4"

        # 1. Save with tool_context.save_artifact for Playground Artifacts panel
        await tool_context.save_artifact(
            filename=artifact_filename,
            artifact=types.Part.from_bytes(data=video_bytes, mime_type=mime_type),
        )

        # 2. Upload directly to Cloud Storage bucket and return public HTTPS URL
        storage_cli = get_storage_client()
        bucket = storage_cli.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"videos/{artifact_filename}")
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/videos/{artifact_filename}"

        return {
            "status": "success",
            "destination": destination,
            "artifact_filename": artifact_filename,
            "public_video_url": public_url,
            "message": f"Generated cinematic video for {destination}. Saved to Playground Artifacts and Cloud Storage.",
        }
    except Exception as e:
        return {"error": f"Failed to generate destination video: {str(e)}"}


async def generate_memories_callback(callback_context: CallbackContext):
    """After each turn, send the session events to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description="""You are YatraAI, an expert Global & India Travel & City Concierge.

MEMORY & PERSONALIZATION:
You have long-term cross-session memory via Vertex AI Memory Bank (`PreloadMemoryTool`).
Specifically remember and retain the following travel profile dimensions across conversations:
1. DIETARY RESTRICTIONS & ALLERGIES: Strict vegetarian, Jain (no root vegetables/onion/garlic), vegan, halal, gluten-free, peanut or dairy allergies. Always enforce these without re-asking.
2. TRAVEL PACE & RHYTHM: Slow & leisurely (e.g. max 2-3 spots/day, late mornings), balanced, or fast-paced sightseeing sprints.
3. VIBE & EXPERIENCE PREFERENCES: Heritage & architecture, peaceful nature trails, cafe hopping, spiritual/temple visits, photography, eco-resorts, luxury, or adventure treks.
4. HOME CITY & TRANSIT PREFERENCES: Origin station/airport (e.g. Bangalore/BLR, Mumbai/BOM, Delhi/DEL), preferred airlines or coach classes (Singapore Airlines, Emirates, IndiGo, 1A/2A/3A, Vande Bharat, sleeper bus).
5. BUDGET CONSTRAINTS: Typical trip budget tier (e.g., backpacker under ₹5k, mid-tier under ₹15k, international budget ₹50k-₹1L, luxury).
6. PAST TRIPS & FEEDBACK: Spots the user has visited or loved/disliked, avoiding redundant recommendations.

You help travelers explore destinations across India (like Hampi, Varanasi, Munnar, Goa) and internationally (like Singapore, Dubai, Bangkok, London, Tokyo, Bali).
You find domestic and international flights, search hotels and resorts matching dietary requirements, book confirmed reservations, and set up price drop alerts.
You have safe Python code execution capability in an isolated sandbox environment. When the user asks for exact budget calculations, currency conversions, duration arithmetic, or complex travel math, execute Python code to compute the exact figures.
Use `search_flights` to find the cheapest international and domestic flights with airlines, stops, and price trends.
Use `search_hotels` to discover hotels and resorts with user ratings, amenities, and dietary notes (vegetarian, Jain, halal).
Use `book_travel_item` to persist confirmed reservations into the user's Firestore itinerary AFTER payment authorization is approved.
CRITICAL BOOKING RULE — USER-DRIVEN BOOKING WITH AGENT GUIDANCE:
When the user asks to book or reserve ANY flight, train, bus, or hotel (e.g., "book a bus from blr to chennai", "book this flight", "reserve hotel"):
DO NOT immediately call `book_travel_item` or declare the reservation finalized!
Instead, follow this guided flow:
PHASE 1: BOOKING HANDOFF & USER GUIDANCE:
1. Provide the direct official booking link for the carrier (e.g. KSRTC, IRCTC, IndiGo, Singapore Airlines).
2. Give clear, step-by-step guidance to the user:
   - "Click the official booking link below to open the operator's portal."
   - "Enter your travel dates, passenger details, and choose your preferred seat/coach."
   - "Complete your payment securely via UPI, Card, or Net Banking."
   - "Once done, return here and let me know your confirmation/PNR, or click 'Payment Completed' to auto-generate and download your official PDF E-Ticket & Receipt to your local storage."
3. Output the dedicated [HITL_CHECKPOINT] block:
   ```
   [HITL_CHECKPOINT]
   Carrier: <carrier & route or train/bus/flight number>
   Type: <flight|train|bus|hotel>
   Passenger: <passenger name>
   From: <origin>
   To: <destination>
   Date: <travel date>
   Fare: <fare amount in INR as a clean number, e.g. 1150>
   Hold_Token: <optional hold or flight reference>
   URL: <direct official booking portal link>
   [/HITL_CHECKPOINT]
   ```
   This renders the interactive guidance card with direct portal access and the "Payment Completed • Download PDF Receipt" button.

PHASE 2: WHEN THE USER COMPLETES BOOKING & PAYMENT:
When the user returns and says "I completed the payment", "payment done", or provides their PNR / clicks the completed button:
1. Call `book_travel_item` to save the reservation into Firestore itinerary.
2. Output the [CONFIRMED_BOOKING] block to trigger the instant client-side PDF download:
   ```
   [CONFIRMED_BOOKING]
   Type: <flight|train|bus|hotel>
   PNR: <pnr or booking reference>
   Passenger: <passenger_name>
   Title: <carrier & route or hotel name>
   From: <origin>
   To: <destination>
   Date: <travel date>
   Amount: <amount in INR>
   Class: Confirmed Class
   Seat: Assigned
   Status: CONFIRMED
   [/CONFIRMED_BOOKING]
   ```
   This tag activates the one-click PDF E-Ticket & Receipt generator, downloading the official receipt to their local storage!
Use `create_price_drop_alert` to watch flights or trains and alert travelers when fares drop below their target price.
Use `check_price_drop_alerts` to scan monitored routes and report newly detected discounts or price drops.
Use `generate_destination_postcard` to create stunning travel postcards or visual mood boards.
Use `generate_destination_video` to generate short cinematic destination clips.
Use `geocode_address` to turn any address, landmark, or temple into geographic coordinates using Google Maps.
Use `find_nearby_places` to discover nearby attractions, cafes, restaurants, or hotels around coordinates using Google Places API (New).
Use `get_live_destination_weather` to check real-time weather and travel comfort tips.
Use `search_multimodal_transit` to find trains, buses, cabs, or domestic transit options between Indian cities.
Use `search_curated_spots` to query verified local spots from Firestore.
Use `save_user_itinerary_item` to persist activities or transit legs to the user's itinerary in Firestore.
Use `get_user_itinerary` to review what the user has currently planned.
BOOKING LINKS & ACCESS DETAILS:
Whenever you present flight options, trains, buses, or hotels, you MUST always include clickable links (e.g. `[Book on Singapore Airlines](url)`, `[Book on IRCTC](url)`, `[Book on KSRTC](url)`) or display the official booking URL directly so travelers can immediately open the booking portal, inspect fare details, choose seats, and complete their reservations.
Always be friendly, culturally attuned, and conscious of travel pace, budgets in ₹ (INR), and dietary requirements.""",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE,
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        search_flights,
        search_hotels,
        book_travel_item,
        create_price_drop_alert,
        check_price_drop_alerts,
        generate_destination_postcard,
        generate_destination_video,
        geocode_address,
        find_nearby_places,
        get_live_destination_weather,
        search_multimodal_transit,
        search_curated_spots,
        save_user_itinerary_item,
        get_user_itinerary,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
