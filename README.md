# AppIntel AI — SaaS Integration Readiness Research

AppIntel AI is a research and evidence-collection project designed to evaluate the integration readiness of 100 SaaS and developer applications across 10 product categories.

The project uses a Python research pipeline to inspect official application and developer documentation, identify evidence signals related to authentication, API access, API coverage and Model Context Protocol (MCP), and present the collected results through an interactive web dashboard.

## Project Objectives

- Research 100 applications across 10 product categories.
- Identify documented authentication methods.
- Investigate self-service versus restricted API access.
- Discover REST, GraphQL and other API documentation.
- Identify official MCP documentation and references.
- Collect evidence URLs for further review.
- Highlight integration blockers and areas requiring manual verification.

## Technology Stack

| Component | Technology |
|---|---|
| Research pipeline | Python |
| Dashboard | HTML, CSS, JavaScript |
| Research data | JSON and CSV |
| Version control | Git and GitHub |
| Deployment | GitHub Pages |

## Project Architecture

1. The Python research agent reads the application research dataset.
2. It visits application websites and discovers relevant documentation pages.
3. It collects metadata and keyword-based evidence signals.
4. It exports research results into timestamped JSON and CSV files.
5. The web dashboard loads the selected JSON report and displays application-level research results.

## Research Dimensions

- **Authentication:** OAuth, API keys, tokens and other authentication references.
- **API Access:** Evidence related to account requirements, credentials, approval and access restrictions.
- **API Surface:** REST, GraphQL and other documented API interfaces.
- **MCP:** Evidence of Model Context Protocol documentation or server availability.
- **Buildability:** Integration feasibility and blockers requiring human assessment.

## Running the Project

### 1. Clone the repository

```bash
git clone https://github.com/sudeeksha-139/AppIntel-AI-starter.git
cd AppIntel-AI-starter
```

### 2. Create and activate a Python virtual environment

```bash
python -m venv venv
```

Windows PowerShell:

```powershell
venv\Scripts\Activate.ps1
```

### 3. Install dependencies

Install the packages listed in the project's dependency file, if provided.

### 4. Run the research pipeline

```bash
python research_agent/main.py
```

The pipeline generates timestamped JSON and CSV reports inside the `reports/` directory.

### 5. Run the dashboard locally

From the project root, start a local static server:

```bash
python -m http.server 5500
```

Open:

```text
http://localhost:5500/
```

The dashboard is also published through GitHub Pages.

## Latest Research Run

The November 26, 2026 research run processed 100 applications.

- Successful homepage responses: 89
- Failed or blocked homepage responses: 11
- Authentication keyword signals: 42
- API surface keyword signals: 41
- MCP keyword signals: 29
- API access keyword signals: 0

These figures represent automated keyword matches, not independently verified product capabilities.

## Manual Verification

A sample of 10 applications was manually reviewed against official documentation.

The sample remains partially verified. An accuracy percentage has not been established because the automated findings have not been fully evaluated as correct or incorrect.

## Limitations

- Website access can fail because of network errors, HTTP restrictions or unavailable pages.
- Keyword matches are indicators for further investigation, not proof of a capability.
- No keyword match does not establish that a capability is unavailable.
- API access requirements may vary by account, plan, region and organization policy.
- Buildability verdicts and integration blockers require manual assessment.
- MCP references should be checked against official documentation before making implementation decisions.

## Live Dashboard

[Open AppIntel AI Dashboard](https://sudeeksha-139.github.io/AppIntel-AI-starter/)

## GitHub Repository

[View Source Code](https://github.com/sudeeksha-139/AppIntel-AI-starter)

## Author

**Sudeeksha M. G.**

AppIntel AI — AI Product Operations Take-Home Assignment.
