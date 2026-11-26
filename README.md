# AppIntel AI — starter

A source-first research collector for the 100 apps in the supplied assignment.

## Setup (Windows PowerShell)

```powershell
cd AppIntel-AI
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python research_agent\main.py
```

If PowerShell blocks activation, run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## Outputs
- `reports/apps_enriched.json`
- `reports/apps_enriched.csv`
- `dashboard/index.html`

Open `dashboard/index.html` in a browser for the starter case-study page.

## Important research-integrity note
The collector fetches the starting URL and records title, meta description, HTTP status and keyword signals. It does **not** establish auth methods, pricing gates, API breadth, MCP support or buildability. Those fields remain `Not verified` until you inspect the official documentation and add evidence. Do not report accuracy or patterns until a real sample has been checked.

## Composio / model integration
This starter does not require Gemini or OpenAI, so temporary model outages or API billing do not block the collection step. You can document the existing Composio connection separately, but do not claim that it researched all 100 apps unless you actually wire and run that workflow.
