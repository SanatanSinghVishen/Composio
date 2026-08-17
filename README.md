# Composio 100-App API Intelligence Research

> Automated SaaS API research across 100 apps for AI agent toolkit buildability — built for the Composio AI Product Ops Intern assignment.

## Live Demo

**[View the Research Report →](https://your-username.github.io/composio-100-app-research/)**

---

## What This Does

An automated research pipeline that evaluates 100 SaaS applications across 10 categories for their suitability as AI agent toolkits. For each app, it discovers:

- **Auth method**: OAuth2, API Key, Basic Auth, Token, or other
- **Access model**: Self-serve (free/paid), trial, or enterprise-gated
- **API surface**: REST/GraphQL, breadth, core resources
- **MCP status**: Whether an MCP server already exists (Official/Community/None)
- **Buildability verdict**: Viability score (0-100) and implementation tier

Then it finds **patterns** across all 100: which auth dominates, which categories are most self-serve, the most common blockers, and where the easy wins are.

## Key Findings

| Metric | Value |
|:---|:---|
| API Key/Token dominates | 45% of apps (vs 34% OAuth2) |
| Self-serve rate | 74% of apps |
| MCP coverage | 95% have Official or Community MCP |
| Average viability | 89.4 / 100 |
| Easy wins | 58 apps (score ≥ 90, self-serve) |
| Buildable today | 87 out of 100 (87%) |

## Architecture

```
┌───────────────┐     ┌──────────────────┐     ┌────────────────┐
│  100 Apps     │────▶│  Composio SDK    │────▶│  OpenRouter    │
│  Input List   │     │  • Exa Search    │     │  Gemini Flash  │
│               │     │  • Firecrawl     │     │  (extraction)  │
└───────────────┘     └──────────────────┘     └────────┬───────┘
                                                         │
                      ┌──────────────────┐     ┌────────▼───────┐
                      │  Verification    │◀────│  Structured    │
                      │  • Self-check    │     │  JSON Results  │
                      │  • Cross-ref     │     └────────────────┘
                      │  • Human check   │
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐
                      │  HTML Report     │
                      │  Single page     │
                      │  Interactive     │
                      └──────────────────┘
```

**Hybrid approach**: Composio SDK handles web search (Exa) and web scraping (Firecrawl). Custom Python orchestrates the pipeline. OpenRouter routes to the best LLM for each stage.

## Tech Stack

| Layer | Technology |
|:---|:---|
| **LLM (bulk)** | Google Gemini 2.5 Flash via OpenRouter |
| **LLM (verify)** | Claude Sonnet 4 via OpenRouter |
| **Web Search** | Exa via Composio SDK |
| **Web Scraping** | Firecrawl via Composio SDK |
| **Orchestration** | Python 3.11+ |
| **Frontend** | Vanilla HTML/CSS/JS + ApexCharts |
| **Deployment** | GitHub Pages |

## How to Run

### Prerequisites
- Python 3.11+
- [OpenRouter](https://openrouter.ai) API key
- [Composio](https://composio.dev) API key (free tier)

### Setup

```bash
# Clone the repo
git clone https://github.com/your-username/composio-100-app-research.git
cd composio-100-app-research

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Authenticate Composio
composio login
composio add exa
composio add firecrawl
```

### Run the Research Pipeline

```bash
# Test on 5 apps first
python agent/research_pipeline.py --dry-run --apps 5

# Run full pipeline (all 100 apps)
python agent/research_pipeline.py

# Run with LLM knowledge only (no Composio)
python agent/research_pipeline.py --skip-composio

# Resume from checkpoint
python agent/research_pipeline.py --resume

# Verify existing results
python agent/research_pipeline.py --verify-only
```

### Run Pattern Analysis

```bash
python analysis/pattern_analyzer.py
```

### Deploy

```bash
# Push to GitHub and enable Pages on the deliverable/ directory
git add .
git commit -m "Research complete"
git push origin main
```

## Project Structure

```
composio-100-app-research/
├── README.md                     # This file
├── requirements.txt              # Python dependencies
├── .env.example                  # API keys template
├── agent/
│   ├── research_pipeline.py      # Main research orchestrator
│   ├── stages/                   # Pipeline stage modules
│   ├── prompts/                  # LLM prompt templates
│   └── utils/                    # Composio SDK wrappers
├── verification/
│   └── (verification scripts)
├── analysis/
│   └── pattern_analyzer.py       # Pattern extraction & insights
├── data/
│   ├── apps_input.json           # The 100 apps input list
│   ├── research_results.json     # Full research output
│   └── patterns_summary.json     # Computed patterns
└── deliverable/
    └── index.html                # THE single-page HTML report
```

## Where the Human Was Needed

The agent struggled with:
1. **Apps with no public docs**: Fanbasis had no discoverable API documentation
2. **Enterprise-gated apps**: DealCloud, PitchBook, Gladly — couldn't verify API details without accounts
3. **Nuanced auth flows**: Salesforce Connected App setup vs simple API key distinction
4. **MCP verification**: Distinguishing "official" from "community" MCP servers required human judgment
5. **Access model precision**: "Free developer sandbox available" vs "API is a paid add-on" edge cases

These were flagged for manual review and documented honestly in the report.

## Verification

Multi-pass accuracy progression:
- **Pass 1 (Agent)**: ~71% accuracy on auth, access, and API surface
- **Pass 2 (Self-check)**: ~79% after LLM cross-validation
- **Pass 3 (Cross-ref)**: ~87% after multi-source verification
- **Final (Human)**: ~92% after manual spot-check of 15 apps

Full verification details are in the HTML report's Verification section.

## License

MIT
