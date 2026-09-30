# 🛺 YatraAI — Autonomous Global & India Travel Concierge

[![Google ADK](https://img.shields.io/badge/Google_ADK-2.6.0+-4285F4?style=flat&logo=google)](https://github.com/google/adk-python)
[![Vertex AI Agent Runtime](https://img.shields.io/badge/Vertex_AI-Agent_Runtime-34A853?style=flat&logo=googlecloud)](https://cloud.google.com/vertex-ai)
[![Gemini Models](https://img.shields.io/badge/Gemini-3.6_Flash_%7C_Omni_%7C_Image-8E75C4?style=flat&logo=googlegemini)](https://deepmind.google/technologies/gemini/)
[![A2A Protocol](https://img.shields.io/badge/Protocol-A2A_1.0_%2B_A2UI_0.8-FF6D00?style=flat)](https://github.com/google/a2a)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**YatraAI** is an autonomous, multimodal travel and city concierge built with the **Google Agent Development Kit (ADK)** and deployed to **Google Cloud Vertex AI Agent Platform (Agent Runtime)** using the **Agent-to-Agent (A2A)** protocol.

From international routes (Singapore, Dubai, London, Tokyo, Bangkok) to Indian heritage trails (Hampi, Varanasi, Munnar, Goa), YatraAI curates tailored itineraries, verifies dietary requirements across chat sessions, grounds recommendations in live web schedules and weather data, and safely orchestrates travel reservations through a **2-Phase Human-in-the-Loop (HITL)** flow with **instant client-side PDF ticketing**.

---

## 🌟 Key Capabilities & Features

### 1. 🧠 Cross-Session Memory (Vertex AI Memory Bank)
* Powered by `PreloadMemoryTool` and post-turn session analysis (`generate_memories_callback`).
* Seamlessly remembers travel preferences across independent sessions without re-asking:
  * **Dietary Needs**: Strict Pure Veg, Jain (no root vegetables/onion/garlic), Halal, Vegan, gluten-free, allergy alerts.
  * **Travel Rhythm & Pace**: Relaxed/leisurely (2–3 spots/day) vs. fast-paced sightseeing.
  * **Vibe Preferences**: UNESCO heritage, tranquil nature trails, cafe hopping, temple tours, luxury resorts.
  * **Transit & Budget Habits**: Preferred home hub (e.g. BLR, DEL, BOM), favored cabin tiers (Economy, Vande Bharat Executive, AC Sleeper), and budget ceilings.

### 2. ✈️ Global Flight Discovery & Domestic Transit
* **International & Domestic Flights (`search_flights`)**: Searches airlines across worldwide hubs with real-time price trend insights (*"Lowest in 30 days"*, *"Recent price drop"*, *"Fares rising"*), baggage rules, and airline meal codes (`AVML`, `VJML`, `Vegan`, `Halal`).
* **Indian Multimodal Transit (`search_multimodal_transit`)**: Aggregates Indian Railways (Vande Bharat, Superfast Expresses), state bus networks (KSRTC Airavat Multi-Axle sleepers), and intercity cabs.
* **Live Web Intelligence (`search_live_travel_web`)**: Live web scraping via DuckDuckGo for up-to-the-minute train running statuses, bus timetables, and unindexed deal portals.

### 3. 🏨 Hotels & Heritage Accommodations (`search_hotels`)
* Curated accommodations ranging from international resorts (Marina Bay Sands, Atlantis The Palm, Amari Watergate) to Indian palaces and estates (BrijRama Palace Varanasi, Evolve Back Kamalapura Palace Hampi, Windermere Estate Munnar).
* Certified dining compatibility filtering (100% Pure Veg, in-house Jain chef, Halal certified).

### 4. 🛡️ 2-Phase Human-in-the-Loop (HITL) Guided Booking
To prevent unintended transactions and uphold traveler safety, YatraAI employs a structured 2-phase reservation protocol:
* **Phase 1: Operator Handoff & Guided Checkpoint (`[HITL_CHECKPOINT]`)**:
  * Emits structured parameters (Carrier, Route, Date, Fare, and Direct Official Portal URL).
  * The frontend renders an interactive **Guided Checkpoint Card** with a 3-step progress tracker and direct portal access (`🌐 Open Official Booking Site ↗`).
* **Phase 2: Confirmation & Instant PDF E-Ticket (`[CONFIRMED_BOOKING]`)**:
  * Once the traveler completes checkout on the carrier portal and confirms, YatraAI issues a confirmed PNR (e.g. `FLI-9A21BF`, `TRN-88EF1C`, `BUS-21AC90`), records the booking in Firestore, and triggers the client-side PDF ticketing engine.

### 5. 🎫 Client-Side PDF E-Ticket & Receipt Generator
* Built with `jsPDF` and `jspdf-autotable` directly inside the browser.
* Generates an official, publication-quality A4 PDF tax invoice and boarding pass containing:
  * Brand header and invoice timestamp.
  * Confirmation status banner and PNR badge.
  * Passenger, route, schedule, seat, and fare breakdown table.
  * Verification barcode token.
  * Carrier baggage, reporting time, and check-in regulations.
* Immediately downloads `YatraAI_Ticket_<PNR>.pdf` to the traveler's local storage.

### 6. 🎨 Multimodal Media Generation
* **Visual Postcards (`generate_destination_postcard`)**: Creates stylized destination artwork and mood boards via `gemini-3.1-flash-lite-image`. Uploads binaries to Google Cloud Storage (`yatra-ai-media-...`) and registers them in the ADK Artifacts panel.
* **Cinematic Destination Video (`generate_destination_video`)**: Generates 4K documentary-style motion clips using Google's Omni model (`gemini-omni-flash-preview`) in the `global` region.

### 7. 🌤️ Weather Grounding & 🗺️ Geospatial Intelligence
* **Live Weather (`get_live_destination_weather`)**: Open-Meteo API integration providing current temperature (°C), conditions, humidity, precipitation, and actionable travel comfort advice (e.g. hydration reminders, rain gear warnings).
* **Google Maps Platform (`geocode_address` & `find_nearby_places`)**: Uses Geocoding API and Places API (New) to locate coordinates and discover tourist attractions, cafes, and temples within customizable radii.

### 8. 🧮 Isolated Code Execution Sandbox
* Equipped with `AgentEngineSandboxCodeExecutor` for executing Python code in an isolated sandbox environment, ensuring exact currency conversions, budget splits, and transit arithmetic.

---

## 🏗️ Architecture & Component Flow

```mermaid
flowchart TD
    subgraph Client["Traveler Interface (Browser SPA)"]
        UI["Modern Web UI\n(HTML5 / CSS3 / Vanilla JS)"]
        PDF["Client-Side PDF Engine\n(jsPDF + AutoTable)"]
        Storage["Local Storage\n(Multi-Chat History & Themes)"]
        A2UI_R["A2UI v0.8 Mini-Renderer\n(Cards, Badges, Columns)"]
        UI --> PDF
        UI --> Storage
        UI --> A2UI_R
    end

    subgraph Proxy["Frontend Proxy (FastAPI :8080)"]
        ProxyServer["main.py Proxy"]
        ADC["Google Cloud ADC\n(OAuth2 Bearer Tokens)"]
        A2A_C["a2a-sdk Client"]
        ProxyServer --> ADC
        ProxyServer --> A2A_C
    end

    subgraph Cloud["Google Cloud Vertex AI Agent Platform"]
        Runtime["Vertex AI Agent Runtime\n(Reasoning Engine Container)"]
        subgraph AgentApp["app/"]
            FastAPIApp["app/fast_api_app.py\n(ADK Runner + A2A Routes)"]
            AgentLogic["app/agent.py\n(gemini-3.6-flash)"]
            A2UI_Utils["app/a2ui_utils.py"]
            BrowserAuto["app/browser_automation.py\n(Playwright Worker)"]
        end
        Runtime --> FastAPIApp
        FastAPIApp --> AgentLogic
        AgentLogic --> A2UI_Utils
    end

    subgraph Services["Backing Cloud Services & Integrations"]
        MemBank[("Vertex AI Memory Bank\n(User Preferences)")]
        Firestore[("Cloud Firestore\n(curated_spots, itinerary_items, price_alerts)")]
        GCS[("Cloud Storage Buckets\n(Postcards & Videos)")]
        Sandbox["Agent Engine Sandbox\n(Python Code Execution)"]
        LiveWeb["DuckDuckGo Live Search\n(Live Transit & Fares)"]
        WeatherAPI["Open-Meteo API\n(Live Weather)"]
        MapsAPI["Google Maps Platform\n(Geocoding & Places New)"]
        Imagen["gemini-3.1-flash-lite-image"]
        Omni["gemini-omni-flash-preview"]
    end

    UI <-->|HTTP /chat| ProxyServer
    A2A_C <-->|A2A Protocol (JSON-RPC over Passthrough)| Runtime
    AgentLogic <--> MemBank
    AgentLogic <--> Firestore
    AgentLogic <--> GCS
    AgentLogic <--> Sandbox
    AgentLogic <--> LiveWeb
    AgentLogic <--> WeatherAPI
    AgentLogic <--> MapsAPI
    AgentLogic <--> Imagen
    AgentLogic <--> Omni
```

---

## 💻 The Web Interface

The frontend (`frontend/static/index.html`) is a tailored, responsive Single Page Application:
* **Exotic World Wallpapers**: Automatically rotates between high-resolution curated destination backdrops (Santorini, Kyoto Arashiyama, Amalfi Coast, Bora Bora, Swiss Alps, Dubai Marina, Ubud Bali, Hampi) with a dynamic destination tag.
* **Light & Dark Theme Engine**: Crisp solid-white card mode and obsidian slate dark mode, toggled with an interactive emoji indicator (🌞 / 🌙).
* **Multi-Conversation History Sidebar**: Collapsible conversation drawer (☰ / ❮) preserving chat sessions in `localStorage`, auto-titling threads from the first prompt, and supporting new chats (`+ New Chat`) and deletions.
* **Interactive Smart Booking Badges**: Detects booking URLs and converts them into branded pill buttons with departure icons.
* **A2UI v0.8 Component Support**: Renders cards, rows, columns, text styles, dividers, and images emitted by the agent model.

---

## 📂 Repository Structure

```
├── app/                                    # Core agent application
│   ├── __init__.py
│   ├── a2ui_utils.py                       # A2UI response wrapper and surface validator
│   ├── agent.py                            # YatraAI core definition, prompt, and 16+ tools
│   ├── browser_automation.py               # Playwright headless browser worker for booking portals
│   ├── fast_api_app.py                     # Container entrypoint with ADK runner & A2A routes
│   └── app_utils/                          # Shared services & protocol adapters
│       ├── a2a.py                          # A2A dynamic agent card and JSON-RPC dispatch
│       ├── reasoning_engine_adapter.py     # Vertex AI Reasoning Engine HTTP adapter
│       └── services.py                     # Process-wide Vertex AI Session, GCS & Memory Bank singletons
├── frontend/                               # Web UI and reverse proxy
│   ├── main.py                             # FastAPI ADC proxy talking to deployed A2A agent
│   ├── requirements.txt                    # Minimal proxy dependencies
│   └── static/
│       └── index.html                      # Single Page Application (CSS3, jsPDF, A2UI renderer)
├── deployment/                             # Infrastructure as Code
│   └── terraform/                          # Terraform manifests (Vertex AI Reasoning Engine, IAM, Telemetry, GCS)
├── tests/                                  # Test & evaluation suites
│   ├── unit/                               # Fast unit tests
│   ├── integration/                        # E2E server & agent stream tests
│   └── eval/                               # LLM-as-a-judge response quality evaluations
├── agents-cli-manifest.yaml                # agents-cli deployment configuration
├── Dockerfile                              # Production container image
├── pyproject.toml                          # Project dependencies and tool configurations
├── record_demo.py                          # Automated Playwright test & recording script
├── generate_chat_pdf.py                    # Transcripts-to-PDF export utility
└── seed_firestore.py                       # Firestore curated spots database seeding script
```

---

## 🚀 Getting Started

### Prerequisites
* Python 3.11 or 3.12
* [uv](https://github.com/astral-sh/uv) (recommended) or `pip`
* Google Cloud CLI (`gcloud`) authenticated to a project with Vertex AI and Firestore enabled

### 1. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/Jeevanthikashyap/buildwithgemini-yatra-ai.git
cd buildwithgemini-yatra-ai

# Install agent dependencies
uv sync

# Install frontend proxy dependencies
pip install -r frontend/requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the project root:
```env
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-east1
GOOGLE_CLOUD_AGENT_ENGINE_LOCATION=us-east1

# Optional: Google Maps Platform API key for Places & Geocoding
GOOGLE_MAPS_API_KEY=your-maps-api-key
```

### 3. Seed Database
Populate Firestore with initial curated spots:
```bash
python seed_firestore.py
```

### 4. Running Locally

#### Option A: Running the Complete Web Interface
1. Launch the local agent server:
   ```bash
   uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000
   ```
2. In a separate terminal, launch the frontend proxy:
   ```bash
   cd frontend
   python main.py
   ```
3. Open your browser at **`http://localhost:8080`**.

#### Option B: Interactive CLI Playground
Test the agent interactively with the Google Agents CLI:
```bash
uv tool install google-agents-cli
agents-cli playground
```

---

## 🧪 Testing & Evaluation

### Run Test Suite
```bash
# Run unit and integration tests
uv run pytest tests/unit tests/integration
```

### Run Quality Evaluations
Grade agent responses against the evaluation dataset using Gemini 3.6 Flash as judge:
```bash
agents-cli eval run --config tests/eval/eval_config.yaml
```

---

## ☁️ Deployment

### Deploy to Vertex AI Agent Platform
Deploy the agent container directly via `agents-cli`:
```bash
agents-cli deploy
```

### Terraform Deployment
To provision the surrounding infrastructure (Reasoning Engine, GCS buckets, BigQuery telemetry pipelines, IAM):
```bash
cd deployment/terraform/single-project
terraform init
terraform apply -var-file=vars/env.tfvars
```

---

## 📄 License
This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for details.

---

**Author**: Jeevanthi Kashyap  
**Repository**: [github.com/Jeevanthikashyap/buildwithgemini-yatra-ai](https://github.com/Jeevanthikashyap/buildwithgemini-yatra-ai)
