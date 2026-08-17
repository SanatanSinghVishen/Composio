"""
Pattern Analyzer — Extracts insights from the 100-app research data.
Generates chart-ready JSON and summary statistics.

Usage:
    python analysis/pattern_analyzer.py
"""

import json
from pathlib import Path
from collections import Counter, defaultdict

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


def load_results():
    with open(DATA_DIR / "research_results.json") as f:
        return json.load(f)


def analyze_auth_distribution(apps):
    """Count auth methods across all apps."""
    auth_counts = Counter()
    for app in apps:
        primary = app.get("auth_primary", "Unknown")
        # Normalize
        if "OAuth" in primary or "OAuth2" in primary:
            auth_counts["OAuth2"] += 1
        elif "API Key" in primary or "API Token" in primary or "PAT" in primary:
            auth_counts["API Key / Token"] += 1
        elif "Basic" in primary:
            auth_counts["Basic Auth"] += 1
        elif "Bearer" in primary or "Bot Token" in primary:
            auth_counts["Bearer / Bot Token"] += 1
        elif primary in ("None", "Other"):
            auth_counts[primary] += 1
        else:
            auth_counts["Other"] += 1
    return dict(auth_counts.most_common())


def analyze_access_by_category(apps):
    """Distribution of access models per category."""
    cat_access = defaultdict(lambda: Counter())
    for app in apps:
        cat = app["category"]
        access = app.get("access_model", "Unknown")
        # Normalize
        if "Self-Serve Free" in access:
            cat_access[cat]["Self-Serve Free"] += 1
        elif "Self-Serve Paid" in access:
            cat_access[cat]["Self-Serve Paid"] += 1
        elif "Free Trial" in access:
            cat_access[cat]["Free Trial"] += 1
        elif "Gated" in access:
            cat_access[cat]["Gated"] += 1
        else:
            cat_access[cat]["Unknown"] += 1
    return {cat: dict(counts) for cat, counts in cat_access.items()}


def analyze_scores_by_category(apps):
    """Average viability score per category."""
    cat_scores = defaultdict(list)
    for app in apps:
        cat = app["category"]
        score = app.get("viability_score", 0)
        if isinstance(score, (int, float)):
            cat_scores[cat].append(score)
    return {cat: round(sum(scores) / len(scores), 1) for cat, scores in cat_scores.items()}


def analyze_mcp_distribution(apps):
    """MCP status distribution."""
    mcp_counts = Counter()
    for app in apps:
        status = app.get("mcp_status", "Unknown")
        mcp_counts[status] += 1
    return dict(mcp_counts.most_common())


def analyze_blockers(apps):
    """Most common blockers."""
    blocker_counts = Counter()
    for app in apps:
        blocker = app.get("primary_blocker", "None")
        if blocker and blocker != "None":
            # Normalize common blockers
            blocker_lower = blocker.lower()
            if "oauth" in blocker_lower:
                blocker_counts["OAuth complexity"] += 1
            elif "enterprise" in blocker_lower or "gated" in blocker_lower:
                blocker_counts["Enterprise/gated access"] += 1
            elif "paid" in blocker_lower or "subscription" in blocker_lower:
                blocker_counts["Requires paid plan"] += 1
            elif "no public" in blocker_lower or "no api" in blocker_lower or "no official" in blocker_lower:
                blocker_counts["No public API/docs"] += 1
            elif "mcp" in blocker_lower:
                blocker_counts["No MCP server"] += 1
            elif "cli" in blocker_lower or "wrapper" in blocker_lower:
                blocker_counts["Requires custom wrapper"] += 1
            else:
                blocker_counts[blocker[:50]] += 1
    return dict(blocker_counts.most_common(10))


def find_easy_wins(apps):
    """Apps with score >= 90 AND self-serve access."""
    easy_wins = []
    for app in apps:
        score = app.get("viability_score", 0)
        access = app.get("access_model", "")
        if score >= 90 and "Self-Serve" in access:
            easy_wins.append({
                "name": app["name"],
                "category": app["category"],
                "score": score,
                "mcp_status": app.get("mcp_status", "None")
            })
    return sorted(easy_wins, key=lambda x: x["score"], reverse=True)


def find_hard_mode(apps):
    """Apps that are gated AND score < 70."""
    hard_mode = []
    for app in apps:
        score = app.get("viability_score", 0)
        access = app.get("access_model", "")
        if score < 70 and "Gated" in access:
            hard_mode.append({
                "name": app["name"],
                "category": app["category"],
                "score": score,
                "blocker": app.get("primary_blocker", "Unknown")
            })
    return hard_mode


def generate_summary(apps):
    """Generate headline summary statistics."""
    total = len(apps)
    
    # Auth dominance
    auth = analyze_auth_distribution(apps)
    top_auth = max(auth, key=auth.get)
    top_auth_pct = round(auth[top_auth] / total * 100)
    
    # Self-serve rate
    self_serve = sum(1 for a in apps if "Self-Serve" in a.get("access_model", ""))
    self_serve_pct = round(self_serve / total * 100)
    
    # MCP coverage
    mcp = analyze_mcp_distribution(apps)
    mcp_covered = mcp.get("Official", 0) + mcp.get("Community", 0)
    mcp_pct = round(mcp_covered / total * 100)
    
    # Average score
    scores = [a.get("viability_score", 0) for a in apps if isinstance(a.get("viability_score"), (int, float))]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    
    # Easy wins
    easy_wins = find_easy_wins(apps)
    
    # Buildable
    buildable = sum(1 for a in apps if a.get("buildability_verdict") == "Yes")
    
    return {
        "total_apps": total,
        "top_auth": top_auth,
        "top_auth_pct": top_auth_pct,
        "self_serve_pct": self_serve_pct,
        "mcp_coverage_pct": mcp_pct,
        "avg_viability_score": avg_score,
        "easy_wins_count": len(easy_wins),
        "buildable_count": buildable,
        "buildable_pct": round(buildable / total * 100)
    }


def main():
    apps = load_results()
    
    print(f"Loaded {len(apps)} apps\n")
    
    # Generate all analyses
    summary = generate_summary(apps)
    auth = analyze_auth_distribution(apps)
    access = analyze_access_by_category(apps)
    scores = analyze_scores_by_category(apps)
    mcp = analyze_mcp_distribution(apps)
    blockers = analyze_blockers(apps)
    easy_wins = find_easy_wins(apps)
    hard_mode = find_hard_mode(apps)
    
    # Print summary
    print("=" * 50)
    print("  KEY PATTERNS")
    print("=" * 50)
    print(f"  OAuth2 dominance: {summary['top_auth_pct']}% use {summary['top_auth']}")
    print(f"  Self-serve rate: {summary['self_serve_pct']}%")
    print(f"  MCP coverage: {summary['mcp_coverage_pct']}%")
    print(f"  Avg viability score: {summary['avg_viability_score']}/100")
    print(f"  Easy wins: {summary['easy_wins_count']} apps (score>=90, self-serve)")
    print(f"  Buildable today: {summary['buildable_count']}/{summary['total_apps']} ({summary['buildable_pct']}%)")
    
    print(f"\n  Auth Distribution: {auth}")
    print(f"\n  MCP Distribution: {mcp}")
    print(f"\n  Top Blockers: {blockers}")
    print(f"\n  Scores by Category: {scores}")
    print(f"\n  Easy Wins ({len(easy_wins)}):")
    for w in easy_wins[:10]:
        print(f"    {w['name']} ({w['category']}): {w['score']}/100, MCP: {w['mcp_status']}")
    
    # Save patterns
    patterns = {
        "summary": summary,
        "auth_distribution": auth,
        "access_by_category": access,
        "scores_by_category": scores,
        "mcp_distribution": mcp,
        "top_blockers": blockers,
        "easy_wins": easy_wins,
        "hard_mode": hard_mode
    }
    
    output_file = DATA_DIR / "patterns_summary.json"
    with open(output_file, "w") as f:
        json.dump(patterns, f, indent=2)
    print(f"\n[OK] Patterns saved to {output_file}")


if __name__ == "__main__":
    main()
