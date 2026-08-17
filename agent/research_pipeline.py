"""
Composio 100-App API Intelligence Research Agent
=================================================
Hybrid approach: Composio SDK for web search/scraping tools + custom Python orchestration.
Uses OpenRouter as the LLM backend (Gemini Flash for bulk, Claude Sonnet for verification).

Requirements:
    pip install composio-core composio-openai openai python-dotenv

Usage:
    python research_pipeline.py                    # Run full pipeline
    python research_pipeline.py --dry-run --apps 5 # Test on 5 apps
    python research_pipeline.py --resume           # Resume from last checkpoint
"""

import json
import os
import time
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")

# LLM Models via OpenRouter
MODEL_BULK = "google/gemini-2.5-flash"        # Fast, cheap, good at structured extraction
MODEL_VERIFY = "anthropic/claude-sonnet-4-20250514"  # Stronger reasoning for verification

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RESULTS_FILE = DATA_DIR / "research_results.json"
CHECKPOINT_FILE = DATA_DIR / "checkpoint.json"

# Rate limiting
REQUESTS_PER_MINUTE = 30
REQUEST_DELAY = 60 / REQUESTS_PER_MINUTE


# ── OpenRouter Client ─────────────────────────────────────────────────────

def get_openrouter_client():
    """Initialize OpenAI client pointed at OpenRouter."""
    from openai import OpenAI
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )


def llm_call(client, model: str, system_prompt: str, user_prompt: str, 
             temperature: float = 0.1, max_tokens: int = 4000) -> str:
    """Make a single LLM call via OpenRouter."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_headers={
            "HTTP-Referer": "https://composio-research.github.io",
            "X-Title": "Composio 100-App Research Agent"
        }
    )
    return response.choices[0].message.content


# ── Composio Tools Setup ──────────────────────────────────────────────────

def setup_composio_tools():
    """Initialize Composio with Exa (search) and Firecrawl (scraping) tools."""
    try:
        from composio import Composio
        from composio_openai import OpenAIResponsesProvider
        
        composio = Composio(
            api_key=COMPOSIO_API_KEY,
            provider=OpenAIResponsesProvider()
        )
        session = composio.create(
            user_id="research_agent",
            toolkits=["exa", "firecrawl"]
        )
        return composio, session
    except Exception as e:
        print(f"⚠ Composio setup failed: {e}")
        print("  Falling back to direct web search via OpenRouter...")
        return None, None


def search_with_composio(session, query: str) -> list:
    """Use Composio Exa integration for semantic web search."""
    if session is None:
        return []
    try:
        result = session.execute_action(
            action="EXA_SEARCH",
            params={"query": query, "num_results": 5}
        )
        return result.get("results", [])
    except Exception as e:
        print(f"  ⚠ Exa search failed: {e}")
        return []


def scrape_with_composio(session, url: str) -> str:
    """Use Composio Firecrawl integration to scrape a URL to markdown."""
    if session is None:
        return ""
    try:
        result = session.execute_action(
            action="FIRECRAWL_SCRAPE",
            params={"url": url, "formats": ["markdown"]}
        )
        return result.get("markdown", result.get("content", ""))
    except Exception as e:
        print(f"  ⚠ Firecrawl scrape failed: {e}")
        return ""


# ── Research Pipeline Stages ──────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are an expert SaaS API analyst. Given information about a software application, 
extract structured data about its API capabilities for AI agent integration.

You MUST respond with ONLY a valid JSON object (no markdown, no explanation, no code fences).
Be precise and evidence-based. If you cannot determine something, use null rather than guessing.

JSON Schema:
{
  "one_liner": "string - What the app does in one sentence",
  "docs_url": "string - URL to developer/API documentation",
  "auth_methods": ["array of strings - e.g., 'OAuth2 (Authorization Code)', 'API Key', 'Basic Auth'"],
  "auth_primary": "string - The primary/recommended auth method",
  "access_model": "string - One of: Self-Serve Free, Self-Serve Paid, Free Trial, Gated (Enterprise), Gated (Partner)",
  "access_detail": "string - How a developer gets API credentials",
  "free_tier": "boolean - Whether there's a free tier that includes API access",
  "api_paradigm": "string - REST, GraphQL, REST + GraphQL, SOAP, gRPC, or None",
  "api_breadth": "string - Micro (<10 endpoints), Moderate (10-50), Broad (50-200), Mega (200+)",
  "endpoint_estimate": "string - Approximate number of endpoints",
  "core_resources": ["array of strings - Main resource types the API exposes"],
  "has_openapi_spec": "boolean - Whether an OpenAPI/Swagger spec is available",
  "mcp_status": "string - Official, Community, or None",
  "mcp_detail": "string - Brief detail about MCP server availability",
  "viability_score": "integer 0-100 - Weighted score for agent toolkit viability",
  "buildability_verdict": "string - Yes, Partial, or No",
  "primary_blocker": "string - Main blocker for building agent toolkit, or 'None'",
  "implementation_tier": "string - Tier 1 (Adopt Existing), Tier 2 (Auto-Gen), Tier 3 (Custom Wrapper), Tier 4 (Skip)"
}

Scoring rubric for viability_score:
- Auth Ergonomics (25 pts): 25=API Key/PAT, 18=Client Credentials OAuth, 10=Auth Code OAuth, 0=Session/Cookie
- Access Availability (25 pts): 25=Free self-serve, 15=Free trial, 5=Paid only, 0=Contact sales/partner
- Schema Quality (20 pts): 20=OpenAPI spec, 10=Clear HTML docs, 0=Undocumented
- Error/Context Quality (15 pts): 15=Pagination+filtering, 5=Basic pagination, 0=No pagination
- Safety (15 pts): 15=Clear read/write separation, 5=Mixed, 0=Unclear"""


def research_single_app(client, composio_session, app: dict) -> dict:
    """Run the full 6-stage research pipeline for a single app."""
    app_name = app["name"]
    website = app["website"]
    hint = app.get("hint", "")
    
    print(f"\n{'='*60}")
    print(f"  Researching: {app_name} ({website})")
    print(f"{'='*60}")
    
    # ── Stage 1: Discovery ──
    print(f"  [1/6] Discovering docs...")
    search_results = search_with_composio(
        composio_session,
        f"{app_name} API documentation developer docs authentication"
    )
    
    # ── Stage 2-4: LLM-based extraction with search context ──
    print(f"  [2/6] Profiling auth...")
    print(f"  [3/6] Classifying access...")
    print(f"  [4/6] Analyzing API surface...")
    
    search_context = ""
    if search_results:
        search_context = "\n".join([
            f"- {r.get('title', 'N/A')}: {r.get('url', 'N/A')}\n  {r.get('snippet', '')}"
            for r in search_results[:5]
        ])
    
    # Scrape the main docs page if we found one
    docs_content = ""
    if search_results:
        docs_url = search_results[0].get("url", "")
        if docs_url:
            print(f"  [*] Scraping: {docs_url}")
            docs_content = scrape_with_composio(composio_session, docs_url)
            if docs_content:
                docs_content = docs_content[:8000]  # Truncate for context window
    
    extraction_prompt = f"""Research the app "{app_name}" (website: {website}, hint: {hint}).

Search results about this app's API:
{search_context if search_context else "No search results available."}

Scraped documentation content:
{docs_content[:4000] if docs_content else "No scraped content available."}

Based on your knowledge and the above information, extract the structured API intelligence data.
Remember: respond with ONLY a valid JSON object, no markdown code fences."""

    raw_response = llm_call(client, MODEL_BULK, EXTRACTION_SYSTEM_PROMPT, extraction_prompt)
    
    # Parse JSON response
    try:
        # Strip markdown code fences if present
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        extracted = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"  ⚠ JSON parse failed for {app_name}, retrying...")
        retry_prompt = f"Your previous response was not valid JSON. Please respond with ONLY a valid JSON object for {app_name}."
        raw_response = llm_call(client, MODEL_BULK, EXTRACTION_SYSTEM_PROMPT, 
                                 extraction_prompt + "\n\n" + retry_prompt)
        try:
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                cleaned = cleaned.rsplit("```", 1)[0]
            extracted = json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"  ✗ JSON parse failed again. Using fallback.")
            extracted = {
                "one_liner": f"Could not extract - manual review needed",
                "docs_url": f"https://{website}",
                "auth_methods": ["Unknown"],
                "auth_primary": "Unknown",
                "access_model": "Unknown",
                "access_detail": "Agent could not determine",
                "free_tier": None,
                "api_paradigm": "Unknown",
                "api_breadth": "Unknown",
                "endpoint_estimate": "Unknown",
                "core_resources": [],
                "has_openapi_spec": None,
                "mcp_status": "Unknown",
                "mcp_detail": "Needs manual check",
                "viability_score": 0,
                "buildability_verdict": "Unknown",
                "primary_blocker": "Agent extraction failed",
                "implementation_tier": "Unknown"
            }
    
    # ── Stage 5: MCP Check ──
    print(f"  [5/6] Checking MCP servers...")
    mcp_results = search_with_composio(
        composio_session,
        f"{app_name} MCP server Model Context Protocol"
    )
    
    if mcp_results:
        mcp_context = "\n".join([f"- {r.get('title', '')}: {r.get('url', '')}" 
                                  for r in mcp_results[:3]])
        mcp_prompt = f"""Given these search results about MCP servers for {app_name}:
{mcp_context}

What is the MCP status? Respond with ONLY a JSON object:
{{"mcp_status": "Official|Community|None", "mcp_detail": "brief detail"}}"""
        
        mcp_response = llm_call(client, MODEL_BULK, 
                                 "You classify MCP server availability. Respond with ONLY valid JSON.",
                                 mcp_prompt, max_tokens=200)
        try:
            cleaned = mcp_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                cleaned = cleaned.rsplit("```", 1)[0]
            mcp_data = json.loads(cleaned)
            extracted["mcp_status"] = mcp_data.get("mcp_status", extracted.get("mcp_status"))
            extracted["mcp_detail"] = mcp_data.get("mcp_detail", extracted.get("mcp_detail"))
        except:
            pass
    
    # ── Stage 6: Compile verdict ──
    print(f"  [6/6] Computing verdict...")
    
    result = {
        "id": app["id"],
        "name": app_name,
        "category": app["category"],
        "website": website,
        **extracted,
        "evidence_urls": [r.get("url", "") for r in (search_results or [])[:3]],
        "research_timestamp": datetime.now().isoformat(),
        "verification": {
            "pass_1_complete": True,
            "human_verified": False,
            "corrections": []
        }
    }
    
    print(f"  ✓ {app_name}: {extracted.get('buildability_verdict', '?')} "
          f"(score: {extracted.get('viability_score', '?')}/100)")
    
    return result


# ── Verification Stage ────────────────────────────────────────────────────

def verify_results(client, results: list, sample_size: int = 15) -> dict:
    """Run verification pass using a stronger model on a sample."""
    import random
    
    print(f"\n{'='*60}")
    print(f"  VERIFICATION PASS (sampling {sample_size} apps)")
    print(f"{'='*60}")
    
    # Stratified sampling: at least 1 per category
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)
    
    sample = []
    for cat, apps in categories.items():
        sample.append(random.choice(apps))
    
    remaining = sample_size - len(sample)
    pool = [r for r in results if r not in sample]
    sample.extend(random.sample(pool, min(remaining, len(pool))))
    
    verification_results = []
    
    for app_result in sample:
        print(f"\n  Verifying: {app_result['name']}...")
        
        verify_prompt = f"""Cross-check this research data for {app_result['name']} ({app_result['website']}).

Agent's findings:
- Auth: {app_result.get('auth_primary', 'Unknown')} ({', '.join(app_result.get('auth_methods', []))})
- Access: {app_result.get('access_model', 'Unknown')}
- API: {app_result.get('api_paradigm', 'Unknown')}, {app_result.get('api_breadth', 'Unknown')}
- MCP: {app_result.get('mcp_status', 'Unknown')}
- Verdict: {app_result.get('buildability_verdict', 'Unknown')} (score: {app_result.get('viability_score', 0)})

Based on your knowledge of {app_result['name']}'s developer platform, verify each field.
Respond with ONLY a JSON object:
{{
  "app_name": "{app_result['name']}",
  "auth_correct": true/false,
  "auth_correction": "correct value if wrong, null if correct",
  "access_correct": true/false,
  "access_correction": "correct value if wrong, null if correct",
  "api_correct": true/false,
  "api_correction": "correct value if wrong, null if correct",
  "mcp_correct": true/false,
  "mcp_correction": "correct value if wrong, null if correct",
  "verdict_correct": true/false,
  "notes": "any additional notes"
}}"""
        
        verify_response = llm_call(client, MODEL_VERIFY,
            "You are an expert API analyst verifying research data. Be strict and precise. Respond with ONLY valid JSON.",
            verify_prompt, max_tokens=500)
        
        try:
            cleaned = verify_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                cleaned = cleaned.rsplit("```", 1)[0]
            verification = json.loads(cleaned)
            verification_results.append(verification)
            
            fields_checked = ["auth", "access", "api", "mcp", "verdict"]
            correct_count = sum(1 for f in fields_checked if verification.get(f"{f}_correct", False))
            print(f"    {correct_count}/{len(fields_checked)} fields correct")
        except:
            print(f"    ⚠ Verification parse failed")
    
    # Compute accuracy metrics
    total_fields = 0
    correct_fields = 0
    for v in verification_results:
        for field in ["auth", "access", "api", "mcp", "verdict"]:
            if f"{field}_correct" in v:
                total_fields += 1
                if v[f"{field}_correct"]:
                    correct_fields += 1
    
    accuracy = (correct_fields / total_fields * 100) if total_fields > 0 else 0
    
    return {
        "sample_size": len(verification_results),
        "total_fields_checked": total_fields,
        "correct_fields": correct_fields,
        "accuracy_pct": round(accuracy, 1),
        "details": verification_results
    }


# ── Main Pipeline ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Composio 100-App Research Agent")
    parser.add_argument("--dry-run", action="store_true", help="Test mode with limited apps")
    parser.add_argument("--apps", type=int, default=100, help="Number of apps to research")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--verify-only", action="store_true", help="Run verification on existing results")
    parser.add_argument("--skip-composio", action="store_true", help="Skip Composio tools, use LLM knowledge only")
    args = parser.parse_args()
    
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Composio 100-App API Intelligence Research Agent       ║")
    print("║  Hybrid: Composio SDK + OpenRouter LLM                 ║")
    print("╚══════════════════════════════════════════════════════════╝")
    
    # Validate API keys
    if not OPENROUTER_API_KEY:
        print("✗ OPENROUTER_API_KEY not set in .env")
        return
    
    # Initialize clients
    client = get_openrouter_client()
    
    composio_client = None
    composio_session = None
    if not args.skip_composio:
        composio_client, composio_session = setup_composio_tools()
    
    # Load apps
    with open(DATA_DIR / "apps_input.json") as f:
        apps_data = json.load(f)
    
    apps = apps_data["apps"][:args.apps]
    print(f"\n📋 Researching {len(apps)} apps...")
    
    # Load existing results if resuming
    results = []
    completed_ids = set()
    if args.resume and RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            results = json.load(f)
        completed_ids = {r["id"] for r in results}
        print(f"  Resuming: {len(completed_ids)} apps already completed")
    
    if not args.verify_only:
        # Research each app
        for i, app in enumerate(apps):
            if app["id"] in completed_ids:
                print(f"  ⊘ Skipping {app['name']} (already completed)")
                continue
            
            try:
                result = research_single_app(client, composio_session, app)
                results.append(result)
                
                # Checkpoint every 5 apps
                if (i + 1) % 5 == 0:
                    with open(RESULTS_FILE, "w") as f:
                        json.dump(results, f, indent=2)
                    print(f"\n  💾 Checkpoint saved ({len(results)}/{len(apps)} apps)")
                
                # Rate limiting
                time.sleep(REQUEST_DELAY)
                
            except Exception as e:
                print(f"  ✗ Error researching {app['name']}: {e}")
                continue
        
        # Save final results
        with open(RESULTS_FILE, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Research complete: {len(results)} apps saved to {RESULTS_FILE}")
    else:
        # Load existing results for verification
        with open(RESULTS_FILE) as f:
            results = json.load(f)
    
    # Run verification
    print("\n" + "="*60)
    print("  RUNNING VERIFICATION PIPELINE")
    print("="*60)
    
    verification = verify_results(client, results)
    
    verification_file = DATA_DIR / "verification_log.json"
    with open(verification_file, "w") as f:
        json.dump(verification, f, indent=2)
    
    print(f"\n✓ Verification complete:")
    print(f"  Sample size: {verification['sample_size']} apps")
    print(f"  Accuracy: {verification['accuracy_pct']}%")
    print(f"  Saved to: {verification_file}")
    
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  Pipeline Complete!                                     ║")
    print(f"║  Apps researched: {len(results):>3}                                  ║")
    print(f"║  Verification accuracy: {verification['accuracy_pct']:>5}%                       ║")
    print("║  Next: python analysis/pattern_analyzer.py              ║")
    print("╚══════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
