# 🛺 YatraAI — Autonomous India Travel & City Concierge

![YatraAI Demo](demo.gif)

**YatraAI** is an autonomous, multimodal travel concierge for India built on the **Google Agent Development Kit (ADK)** and deployed to **Google Cloud Vertex AI Agent Platform** using the Agent-to-Agent (A2A) protocol.

YatraAI plans, adapts, and manages personalized Indian itineraries (heritage, scenic trails, transit, and authentic food) with real-time transit awareness, long-term memory for dietary and travel preferences, and generative travel media.

---

## 🌟 Capabilities Implemented

The features below are wired directly to Google Cloud services and production tools in [`app/agent.py`](app/agent.py):

- **🧠 Cross-Session Memory (Vertex AI Memory Bank)**:
  - Powered by `PreloadMemoryTool` and an `after_agent_callback` hook (`callback_context.add_session_to_memory()`).
  - Automatically extracts and retains user preferences across independent chat sessions: dietary requirements (pure veg, jain, vegan), preferred travel pace, budget sensitivity, and favorite destinations.

- **🗄️ Curated Spots & Itineraries (Google Cloud Firestore)**:
  - **`search_curated_spots`**: Queries the `curated_spots` collection with filtering for destinations (e.g. Hampi, Munnar, Varanasi), categories (scenic trails, cafes, heritage sites), dietary tags, and vibes.
  - **`save_user_itinerary_item` & `get_user_itinerary`**: Persists approved activities and retrieves structured itinerary items with cost estimates and timestamps.

- **🎨 Generative Postcards & Media (Google Cloud Storage & Vertex AI)**:
  - **`generate_destination_postcard`**: Uses `gemini-3.1-flash-lite-image` to generate high-resolution visual travel postcards, saves them to the Playground Artifacts panel (`tool_context.save_artifact`), and uploads them to a public Cloud Storage bucket.
  - **`generate_destination_video`**: Uses Google's Omni model (`gemini-omni-flash-preview`) in the `global` region to produce cinematic travel clips, saving to Artifacts and uploading to Cloud Storage.

- **✈️ International & Domestic Flight Search (`search_flights`)**:
  - Finds flights across global hubs (Singapore, Dubai, London, Tokyo, Bangkok, Paris) and domestic routes with real-time price trend insights (e.g., "Lowest in 30 days", "Recent price drop", "Fares rising"), baggage rules, and special dietary meal codes (AVML, VJML, Vegan).

- **🏨 Global Hotel Discovery (`search_hotels`)**:
  - Curated stays from heritage palaces to luxury resorts with star ratings, traveler scores, amenity lists, and dietary accommodations (100% pure veg, Jain, Halal certified).

- **🎟️ Autonomous Travel Bookings (`book_travel_item`)**:
  - Automatically issues confirmed booking references (PNR / Reservation IDs) for flights, trains, and hotels, and persists them into the user's Firestore itinerary with refundable terms and travel dates.

- **🔔 Multi-Modal Price Drop Watch & Alerts (`create_price_drop_alert` & `check_price_drop_alerts`)**:
  - Sets up threshold watches for trains and flights (domestic and international) and scans active market discounts, calculating exact savings in ₹ and % drop to advise booking timing.

- **🚂 Multi-Modal Indian Transit Discovery (`search_multimodal_transit`)**:
  - Searches options across trains (Indian Railways / IRCTC), sleeper buses (KSRTC Airavat), intercity cabs, and domestic flights with departure timings, class of travel, and INR (₹) price ranges.

- **🌦️ Live Destination Weather & Alerts**:
  - **`get_live_destination_weather`**: Fetches real-time weather, temperature, humidity, precipitation, and terrain-specific advisory (such as boulder trekking cautions in Hampi or fog warnings in North India).

- **📍 Geocoding & Places Search (Google Maps Platform)**:
  - **`geocode_address`**: Resolves landmarks and addresses to geographic coordinates via the Google Maps Geocoding API.
  - **`find_nearby_places`**: Discovers nearby attractions, restaurants, and temples via the Google Maps Places API (New) `searchNearby` REST endpoint.

- **💻 Python Sandbox Code Execution**:
  - Powered by `AgentEngineSandboxCodeExecutor` running on Vertex AI Agent Engine for calculating complex multi-city currency splits, transit budget reconciliations, and travel mathematics.

- **🎴 Rich Agent-to-UI (A2UI v0.8)**:
  - Generates structured, responsive A2UI cards (Cards, Columns, Rows, Texts, and Images) converted into `<a2a_datapart_json>` via `a2ui_callback`.
  - Natively rendered in both the local ADK Dev UI and the custom chat frontend.

---

## 🏗️ Architecture

```
                                  ┌─────────────────────────────────┐
                                  │      Custom Web Frontend        │
                                  │ (FastAPI Proxy + A2UI Renderer) │
                                  └────────────────┬────────────────┘
                                                   │ A2A Protocol
                                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│               Vertex AI Agent Runtime (Reasoning Engine)              │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                      root_agent (ADK)                          │   │
│   │                 Model: gemini-3.6-flash                        │   │
│   └──────┬────────────┬─────────────┬─────────────┬────────────┬───┘   │
│          │            │             │             │            │       │
│          ▼            ▼             ▼             ▼            ▼       │
│    Memory Bank    Firestore      GenAI API     GenAI API    Sandbox    │
│   (PreloadMemory) (Spots/Itin)   (Postcards)    (Videos)    (CodeExec) │
│                                (flash-lite-img) (omni-flash)           │
└──────────┬────────────┬─────────────┬─────────────┬────────────┬───────┘
           │            │             │             │            │
           ▼            ▼             ▼             ▼            ▼
     Vertex AI     Cloud         Cloud         Cloud        Agent Engine
    Memory Bank   Firestore     Storage       Storage       Code Sandbox
                                (Postcards)   (Videos)
```

---

## 🚀 Local Setup & Running

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Google Cloud SDK (`gcloud`) authenticated with an active project

### 1. Clone & Install Dependencies
```bash
git clone <your-repo-url>
cd yatra-ai

# Install root ADK agent dependencies
uv sync
```

### 2. Configure Environment Variables
Create a `.env` file in the project root:
```bash
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
```

### 3. Launch Local ADK Web Playground
To run the agent with cross-session Memory Bank support in the ADK web development UI:
```bash
uv run adk web . --port 8080 --reload_agents --memory_service_uri=agentengine://<YOUR_AGENT_ENGINE_ID>
```

### 4. Run the Custom A2A Frontend
The repo includes a dedicated lightweight FastAPI proxy and themed chat interface with native A2UI card rendering:
```bash
cd frontend

# Install frontend dependencies
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# Start the frontend proxy
export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUM>/locations/<REGION>/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"
export PORT=8080
./.venv/bin/python main.py
```

---

## 📦 Deployment

### Deploy Agent to Vertex AI Agent Runtime
```bash
uv run agents-cli deploy \
  --project <YOUR_GCP_PROJECT_ID> \
  --no-confirm-project \
  --update-env-vars "GOOGLE_MAPS_API_KEY=your_key"
```

### Deploy Frontend to Cloud Run
```bash
cd frontend
gcloud run deploy yatra-ai-frontend \
  --source . \
  --project <YOUR_GCP_PROJECT_ID> \
  --region us-east1 \
  --set-env-vars "AGENT_ENGINE_RESOURCE_NAME=projects/<PROJECT_NUM>/locations/us-east1/reasoningEngines/<ENGINE_ID>,AGENT_DIRECTORY=app" \
  --allow-unauthenticated
```
