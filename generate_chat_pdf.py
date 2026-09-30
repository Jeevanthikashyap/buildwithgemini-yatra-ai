import json
import html
import re
from playwright.sync_api import sync_playwright

transcript_path = "/config/.gemini/antigravity/brain/be4c90de-9c4e-4c03-a3d8-d03d0e174fd7/.system_generated/logs/transcript.jsonl"
output_html_path = "/config/Desktop/BuildWithGemini/yatra-ai/chat_history.html"
output_pdf_path = "/config/Desktop/BuildWithGemini/yatra-ai/YatraAI_Complete_Project_and_Chat_History.pdf"

entries = []
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue

        source = d.get("source")
        step_type = d.get("type")
        content = d.get("content", "")

        # Skip internal system checkpoints, truncation summaries or background timer heartbeats
        if source == "SYSTEM" and step_type in ("CHECKPOINT", "SYSTEM_MESSAGE"):
            continue

        if step_type == "USER_INPUT" and source == "USER_EXPLICIT":
            # Clean XML tags from user input if present
            clean_content = re.sub(r"<USER_REQUEST>", "", content)
            clean_content = re.sub(r"</USER_REQUEST>", "", clean_content)
            clean_content = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", clean_content).strip()
            if clean_content:
                entries.append({"role": "User", "text": clean_content})

        elif step_type == "PLANNER_RESPONSE" and source == "MODEL":
            # Extract text response intended for user
            # Check if there's textual content
            if content and isinstance(content, str):
                # Remove system artifact tags or noisy internal logs if any
                text = content.strip()
                if text and not text.startswith("<SYSTEM_MESSAGE>"):
                    entries.append({"role": "Assistant (Antigravity)", "text": text})

print(f"Extracted {len(entries)} dialogue exchanges.")

# Merge consecutive entries of the same role if any
merged_entries = []
for e in entries:
    if merged_entries and merged_entries[-1]["role"] == e["role"]:
        merged_entries[-1]["text"] += "\n\n" + e["text"]
    else:
        merged_entries.append(e)

print(f"Total merged conversational turns: {len(merged_entries)}")

# Format Markdown to HTML lightly
def format_text(raw_text):
    # Escape HTML
    t = html.escape(raw_text)
    # Bold
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    # Italic
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    # Inline code
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    # Headers
    t = re.sub(r"^### (.+)$", r"<h4>\1</h4>", t, flags=re.MULTILINE)
    t = re.sub(r"^## (.+)$", r"<h3>\1</h3>", t, flags=re.MULTILINE)
    t = re.sub(r"^# (.+)$", r"<h2>\1</h2>", t, flags=re.MULTILINE)
    # Bullet points
    lines = t.split("\n")
    in_list = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("- ") or line.strip().startswith("* "):
            if not in_list:
                new_lines.append("<ul>")
                in_list = True
            item_text = line.strip()[2:]
            new_lines.append(f"<li>{item_text}</li>")
        else:
            if in_list:
                new_lines.append("</ul>")
                in_list = False
            if line.strip():
                new_lines.append(f"<p>{line}</p>")
    if in_list:
        new_lines.append("</ul>")
    return "\n".join(new_lines)

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>YatraAI — Complete Project & Chat History</title>
<style>
  @page {{
    margin: 20mm 15mm 20mm 15mm;
    @bottom-right {{
      content: counter(page);
    }}
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #2D3748;
    line-height: 1.6;
    background: #fff;
    font-size: 11pt;
  }}
  .cover-header {{
    border-bottom: 3px solid #E65100;
    padding-bottom: 1.5rem;
    margin-bottom: 2rem;
  }}
  .cover-header h1 {{
    color: #E65100;
    font-size: 26pt;
    margin: 0 0 0.3rem 0;
  }}
  .cover-header .subtitle {{
    font-size: 14pt;
    color: #718096;
    margin-bottom: 0.8rem;
  }}
  .meta-box {{
    background: #FFF8E1;
    border-left: 4px solid #FF8F00;
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 10pt;
    color: #5D4037;
    margin-top: 1rem;
  }}
  .chat-turn {{
    margin-bottom: 1.6rem;
    padding: 12px 16px;
    border-radius: 8px;
    page-break-inside: avoid;
  }}
  .chat-turn.user {{
    background: #F0F4F8;
    border-left: 4px solid #3182CE;
  }}
  .chat-turn.assistant {{
    background: #FFFDF9;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #E65100;
  }}
  .role-badge {{
    font-size: 10pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
  }}
  .user .role-badge {{ color: #2B6CB0; }}
  .assistant .role-badge {{ color: #C65102; }}
  p {{ margin: 0 0 0.6rem 0; }}
  p:last-child {{ margin-bottom: 0; }}
  code {{
    background: #EDF2F7;
    padding: 2px 5px;
    border-radius: 3px;
    font-family: Consolas, Monaco, "Courier New", monospace;
    font-size: 9.5pt;
    color: #805AD5;
  }}
  pre {{
    background: #2D3748;
    color: #F7FAFC;
    padding: 10px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 9pt;
  }}
  ul {{ margin: 0 0 0.8rem 1.2rem; padding: 0; }}
  li {{ margin-bottom: 0.3rem; }}
  h2, h3, h4 {{ margin-top: 1rem; margin-bottom: 0.4rem; color: #1A202C; }}
  .footer-note {{
    margin-top: 3rem;
    border-top: 1px solid #E2E8F0;
    padding-top: 1rem;
    font-size: 9pt;
    color: #A0AEC0;
    text-align: center;
  }}
</style>
</head>
<body>

<div class="cover-header">
  <h1>🛺 YatraAI</h1>
  <div class="subtitle">Complete Autonomous Agent Development Log &amp; Conversation Transcript</div>
  <div><strong>Developer / Author:</strong> Jeevanthi Kashyap</div>
  <div><strong>Repository:</strong> https://github.com/Jeevanthikashyap/buildwithgemini-yatra-ai</div>
  <div class="meta-box">
    <strong>Project Architecture Summary:</strong> Google Agent Development Kit (ADK), Vertex AI Agent Platform (Agent Runtime / Reasoning Engine), Google Cloud Firestore, Cloud Storage, Vertex AI Memory Bank (cross-session memory), Google Omni (gemini-omni-flash-preview video generation), Imagen (gemini-3.1-flash-lite-image postcards), Google Maps Platform Places &amp; Geocoding APIs, Agent Engine Python Sandbox, and A2A Protocol with A2UI v0.8.
  </div>
</div>

<div class="transcript-container">
"""

for idx, e in enumerate(merged_entries, 1):
    role_class = "user" if e["role"].startswith("User") else "assistant"
    formatted_body = format_text(e["text"])
    html_content += f"""
  <div class="chat-turn {role_class}">
    <div class="role-badge">Turn {idx} — {e["role"]}</div>
    <div class="turn-content">{formatted_body}</div>
  </div>
"""

html_content += """
</div>

<div class="footer-note">
  Generated from Build With Gemini Workspace • Session ID: be4c90de-9c4e-4c03-a3d8-d03d0e174fd7
</div>

</body>
</html>
"""

with open(output_html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML document generated. Rendering PDF via Playwright Chromium...")

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
    page = browser.new_page()
    page.goto(f"file://{output_html_path}", wait_until="networkidle")
    page.pdf(
        path=output_pdf_path,
        format="A4",
        print_background=True,
        margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"},
        display_header_footer=True,
        header_template='<div style="font-size: 8pt; color: #a0aec0; width: 100%; text-align: right; padding-right: 15mm;">YatraAI — Complete Conversation History</div>',
        footer_template='<div style="font-size: 8pt; color: #a0aec0; width: 100%; text-align: center;">Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>'
    )
    browser.close()

print(f"✓ PDF successfully generated at: {output_pdf_path}")
