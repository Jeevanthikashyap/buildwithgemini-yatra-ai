"""Seed script for YatraAI destinations, curated spots, and trip bookings in Firestore."""

from google.cloud import firestore

# IMPORTANT: Hardcode the project ID as a string, NOT from env or google.auth.default()
# which returns the project number on Agent Platform.
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-04-8017249fc17a"

SEED_SPOTS = [
    {
        "id": "hampi-matanga-hill",
        "name": "Matanga Hill Sunrise Trek",
        "destination": "Hampi",
        "category": "scenic_trail",
        "vibe": ["scenic", "heritage", "sunrise"],
        "pace": "moderate",
        "estimated_duration_hours": 2.5,
        "cost_inr": 0,
        "description": "Highest point in central Hampi offering panoramic 360-degree views of the boulder ruins and Tungabhadra river at sunrise.",
        "dietary_options": ["fresh coconut water", "local chai stalls"],
        "tags": ["boulders", "photography", "panoramic"],
    },
    {
        "id": "hampi-mango-tree",
        "name": "Mango Tree Restaurant",
        "destination": "Hampi",
        "category": "cafe",
        "vibe": ["chill", "riverfront", "heritage"],
        "pace": "slow",
        "estimated_duration_hours": 1.5,
        "cost_inr": 350,
        "description": "Laid-back riverside dining with low floor seating, specialty herbal teas, and authentic thalis.",
        "dietary_options": ["pure vegetarian", "vegan friendly", "jain options available"],
        "tags": ["riverview", "south-indian-thali", "cafe-culture"],
    },
    {
        "id": "hampi-vitthala-temple",
        "name": "Vijaya Vittala Temple & Stone Chariot",
        "destination": "Hampi",
        "category": "heritage_site",
        "vibe": ["heritage", "architecture", "spiritual"],
        "pace": "slow",
        "estimated_duration_hours": 3.0,
        "cost_inr": 50,
        "description": "Architectural masterpiece dating back to the 15th-century Vijayanagara Empire with musical pillars and the iconic stone chariot.",
        "dietary_options": ["water stalls outside"],
        "tags": ["unesco-heritage", "monument", "history"],
    },
    {
        "id": "varanasi-brown-bread-bakery",
        "name": "Brown Bread Bakery & Rooftop",
        "destination": "Varanasi",
        "category": "cafe",
        "vibe": ["bohemian", "quiet", "viewpoint"],
        "pace": "slow",
        "estimated_duration_hours": 1.5,
        "cost_inr": 400,
        "description": "Organic rooftop cafe overlooking the holy ghats serving homemade organic breads, cheeses, and cold pressed juices.",
        "dietary_options": ["organic vegetarian", "vegan friendly", "gluten free"],
        "tags": ["ghat-view", "organic-bakery", "live-classical-music"],
    },
    {
        "id": "varanasi-morning-subah-e-banaras",
        "name": "Subah-e-Banaras at Assi Ghat",
        "destination": "Varanasi",
        "category": "experience",
        "vibe": ["spiritual", "sunrise", "culture"],
        "pace": "slow",
        "estimated_duration_hours": 2.0,
        "cost_inr": 0,
        "description": "A tranquil dawn ritual along Assi Ghat featuring morning raga, Vedic chanting, Ganga aarti, and yoga session.",
        "dietary_options": ["Assi Ghat lemon tea", "kachori sabzi stalls nearby"],
        "tags": ["aarti", "classical-music", "ganga-river"],
    },
    {
        "id": "munnar-chokramudi-peak",
        "name": "Chokramudi Peak Cloud Trek",
        "destination": "Munnar",
        "category": "scenic_trail",
        "vibe": ["scenic", "nature", "misty"],
        "pace": "moderate",
        "estimated_duration_hours": 4.0,
        "cost_inr": 400,
        "description": "Isolated peak rising above the tea gardens and shola forests with rolling mist and views of the Anamudi ranges.",
        "dietary_options": ["packed breakfast needed"],
        "tags": ["tea-plantations", "trekking", "clouds"],
    },
]


def seed_database():
    print(f"Connecting to Firestore with project ID: {FIRESTORE_PROJECT_ID}...")
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)

    spots_ref = db.collection("curated_spots")
    batch = db.batch()
    for spot in SEED_SPOTS:
        doc_ref = spots_ref.document(spot["id"])
        batch.set(doc_ref, spot)

    batch.commit()
    print(f"Successfully seeded {len(SEED_SPOTS)} curated spots into 'curated_spots' collection!")


if __name__ == "__main__":
    seed_database()
