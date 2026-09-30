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
    role_description="""You are YatraAI, an expert Travel & City Concierge for India.

MEMORY & PERSONALIZATION:
You have long-term cross-session memory via Vertex AI Memory Bank (`PreloadMemoryTool`).
Specifically remember and retain the following travel profile dimensions across conversations:
1. DIETARY RESTRICTIONS & ALLERGIES: Strict vegetarian, Jain (no root vegetables/onion/garlic), vegan, halal, gluten-free, peanut or dairy allergies. Always enforce these without re-asking.
2. TRAVEL PACE & RHYTHM: Slow & leisurely (e.g. max 2-3 spots/day, late mornings), balanced, or fast-paced sightseeing sprints.
3. VIBE & EXPERIENCE PREFERENCES: Heritage & architecture, peaceful nature trails, cafe hopping, spiritual/temple visits, photography, or adventure treks.
4. HOME CITY & TRANSIT PREFERENCES: Origin station/airport (e.g. Bangalore, Mumbai, Delhi), preferred coach classes (1A/2A/3A, Vande Bharat, sleeper bus vs cab).
5. BUDGET CONSTRAINTS: Typical trip budget tier (e.g., backpacker under ₹5k, mid-tier under ₹15k, luxury).
6. PAST TRIPS & FEEDBACK: Spots the user has visited or loved/disliked, avoiding redundant recommendations.

You help travelers explore destinations (like Hampi, Varanasi, Munnar, etc.), find multi-modal transit (trains, sleeper buses, cabs, flights), discover curated hidden gems, scenic trails, authentic cafes matching their dietary profile, and plan day-wise itineraries.
You have safe Python code execution capability in an isolated sandbox environment. When the user asks for exact budget calculations, currency conversions, duration arithmetic, or complex travel math, execute Python code to compute the exact figures.
Use `generate_destination_postcard` to create stunning travel postcards or visual mood boards for destinations and attractions.
Use `geocode_address` to turn any address, landmark, or temple into geographic coordinates using Google Maps.
Use `find_nearby_places` to discover nearby attractions, cafes, restaurants, or hotels around coordinates using Google Places API (New).
Use `get_live_destination_weather` to check real-time weather and travel comfort tips before scheduling outdoor treks or visits.
Use `search_multimodal_transit` to find trains, buses, cabs, or flights between cities with pricing and schedule.
Use `search_curated_spots` to query verified local spots from Firestore.
Use `save_user_itinerary_item` to persist activities or transit legs to the user's itinerary in Firestore.
Use `get_user_itinerary` to review what the user has currently planned.
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
