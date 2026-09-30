import os
import time
from playwright.sync_api import sync_playwright

def run():
    video_dir = "/config/Desktop/BuildWithGemini/yatra-ai/demo_recordings"
    os.makedirs(video_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=video_dir,
            record_video_size={"width": 1280, "height": 800}
        )
        page = context.new_page()

        print("Navigating to YatraAI frontend...")
        page.goto("http://localhost:8080/")
        page.wait_for_timeout(2500)

        # 1. First prompt: Doing what the app does best - Planning a 3-day itinerary
        print("Submitting prompt 1: 3-day Hampi itinerary...")
        page.fill("#input", "Plan 3 days in Hampi, vegetarian, slow pace, under ₹15,000")
        page.wait_for_timeout(1000)
        page.click("button.send-btn")

        # Wait for agent response to appear
        page.wait_for_selector(".msg-row.agent .a2card, .msg-row.agent .bubble:not(:has-text('…'))", timeout=60000)
        print("Prompt 1 response received!")
        page.wait_for_timeout(4000)

        # Scroll down slightly to admire the rendered card
        page.evaluate("document.getElementById('log').scrollTop = document.getElementById('log').scrollHeight")
        page.wait_for_timeout(2000)

        # 2. Second prompt: Richer prompt showing tool calls, database lookup, and image
        print("Submitting prompt 2: Curated spots database lookup & postcard image...")
        page.fill("#input", "Show me curated vegetarian hidden gems in Hampi from your catalog, and generate a sunset postcard.")
        page.wait_for_timeout(1000)
        page.click("button.send-btn")

        # Wait for second response
        # Find all agent message rows and wait until second agent row finishes
        for _ in range(60):
            agent_rows = page.query_selector_all(".msg-row.agent")
            if len(agent_rows) >= 2:
                last_bubble = agent_rows[-1].query_selector(".bubble")
                if last_bubble and "…" not in (last_bubble.inner_text() or ""):
                    print("Prompt 2 response received!")
                    break
            page.wait_for_timeout(1000)

        page.evaluate("document.getElementById('log').scrollTop = document.getElementById('log').scrollHeight")
        page.wait_for_timeout(5000)

        # Capture high quality screenshot
        page.screenshot(path="/config/Desktop/BuildWithGemini/yatra-ai/demo_screenshot.png", full_page=False)

        # Close page and context to finish video writing
        page.close()
        video_path = page.video.path()
        context.close()
        browser.close()

        print("Raw video saved to:", video_path)
        final_mp4 = "/config/Desktop/BuildWithGemini/yatra-ai/demo_video.mp4"
        os.system(f"ffmpeg -y -i '{video_path}' -c:v libx264 -pix_fmt yuv420p '{final_mp4}'")
        print("Final video created at:", final_mp4)

if __name__ == "__main__":
    run()
