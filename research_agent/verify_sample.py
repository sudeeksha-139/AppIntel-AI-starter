import json
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

input_file = ROOT / "reports" / "apps_enriched.json"
output_file = ROOT / "reports" / "verification_sample.csv"

with open(input_file, encoding="utf-8") as f:
    apps = json.load(f)

sample = []
seen = set()

for app in apps:
    if app["category"] not in seen:
        sample.append(app)
        seen.add(app["category"])

fields = [
    "id",
    "app",
    "category",
    "starting_url",
    "page_title",
    "http_status",
    "agent_auth_finding",
    "human_verified_auth",
    "agent_access_finding",
    "human_verified_access",
    "agent_api_finding",
    "human_verified_api",
    "agent_mcp_finding",
    "human_verified_mcp",
    "correct_or_incorrect",
    "evidence_url",
    "review_notes",
]

with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()

    for app in sample:
        writer.writerow(
            {
                "id": app["id"],
                "app": app["app"],
                "category": app["category"],
                "starting_url": app["starting_url"],
                "page_title": app.get("page_title", ""),
                "http_status": app.get("http_status", ""),
                "agent_auth_finding": "Not established",
                "human_verified_auth": "",
                "agent_access_finding": "Not established",
                "human_verified_access": "",
                "agent_api_finding": "Keyword signals only",
                "human_verified_api": "",
                "agent_mcp_finding": "Not established",
                "human_verified_mcp": "",
                "correct_or_incorrect": "Pending review",
                "evidence_url": "",
                "review_notes": "",
            }
        )

print("Verification CSV corrected!")
print("Sample size:", len(sample))
