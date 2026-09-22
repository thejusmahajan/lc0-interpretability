import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

OPENINGS_DATA_DIR = Path(__file__).parent.parent / "openings_data"
RECOMMENDATIONS_FILE = OPENINGS_DATA_DIR / "sharp_recommendations.json"


def sharpness_by_opening(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Group steer_findings and findings by real ECO (excluding '???').
    
    Returns a list of dicts sorted by (sacs * mean_complexity) DESC:
    [
        {
            "eco": str,
            "name": str,
            "sacs": int,
            "mean_complexity": float,
            "n_positions": int,
            "top_positions": [str, ...], # steer finding IDs sorted by complexity DESC
            "sharpness_score": float
        },
        ...
    ]
    """
    if not profile:
        return []

    steer_findings = profile.get("steer_findings", [])
    findings = profile.get("findings", [])

    eco_groups: Dict[str, Dict[str, Any]] = {}

    def get_eco_entry(eco: str, name: str) -> Dict[str, Any]:
        if eco not in eco_groups:
            eco_groups[eco] = {
                "eco": eco,
                "name": name if name and name != "Unknown" else eco,
                "steer_items": [],
                "finding_items": [],
            }
        elif eco_groups[eco]["name"] == eco and name and name != "Unknown":
            eco_groups[eco]["name"] = name
        return eco_groups[eco]

    for sf in steer_findings:
        opening = sf.get("opening", {})
        eco = opening.get("eco", "???")
        if not eco or eco == "???":
            continue
        name = opening.get("name", "Unknown")
        entry = get_eco_entry(eco, name)
        entry["steer_items"].append(sf)

    for f in findings:
        opening = f.get("opening", {})
        eco = opening.get("eco", "???")
        if not eco or eco == "???":
            continue
        name = opening.get("name", "Unknown")
        entry = get_eco_entry(eco, name)
        entry["finding_items"].append(f)

    results: List[Dict[str, Any]] = []

    for eco, grp in eco_groups.items():
        steer_items = grp["steer_items"]
        finding_items = grp["finding_items"]

        # Sharp position count: steer_findings where had_sharp_move is True
        sharp_items = [sf for sf in steer_items if sf.get("had_sharp_move")]
        sharp_positions = len(sharp_items)

        # Real missed sacrifices from findings motifs (Phase A/B correct)
        missed_sacs = [f for f in finding_items if "sacrifice" in (f.get("motifs") or [])]
        missed_sacrifices = len(missed_sacs)

        # Total positions in this ECO
        n_positions = len(steer_items) + len(finding_items)

        # Mean complexity across steer_findings
        complexities = []
        for sf in steer_items:
            comp = None
            if "steer" in sf and isinstance(sf["steer"], dict) and "complexity" in sf["steer"]:
                comp = sf["steer"]["complexity"]
            elif "best" in sf and isinstance(sf["best"], dict) and "complexity" in sf["best"]:
                comp = sf["best"]["complexity"]
            if comp is not None:
                complexities.append(float(comp))

        mean_complexity = round(sum(complexities) / len(complexities), 4) if complexities else 0.0

        # Top positions: steer finding IDs sorted by complexity DESC
        sorted_steer = sorted(
            steer_items,
            key=lambda sf: (
                1 if sf.get("had_sharp_move") else 0,
                float(sf.get("steer", {}).get("complexity", sf.get("best", {}).get("complexity", 0.0)))
            ),
            reverse=True
        )

        top_positions = []
        seen_ids = set()
        for sf in sorted_steer:
            sf_id = sf.get("id")
            if sf_id and sf_id not in seen_ids:
                seen_ids.add(sf_id)
                top_positions.append(sf_id)
                if len(top_positions) >= 8:
                    break

        sharpness_score = round(sharp_positions * mean_complexity, 4)

        results.append({
            "eco": eco,
            "name": grp["name"],
            "sacs": sharp_positions,
            "sharp_positions": sharp_positions,
            "missed_sacrifices": missed_sacrifices,
            "mean_complexity": mean_complexity,
            "n_positions": n_positions,
            "top_positions": top_positions,
            "sharpness_score": sharpness_score,
        })

    # Sort openings by sharpness_score DESC, then sacs DESC, then eco ASC
    results.sort(key=lambda x: (-x["sharpness_score"], -x["sacs"], x["eco"]))
    return results


def load_recommendations(color: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load dynamic opening recommendations from sharp_recommendations.json."""
    if not RECOMMENDATIONS_FILE.exists():
        return []

    with open(RECOMMENDATIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if color:
        col_lower = color.lower().strip()
        data = [item for item in data if item.get("color", "").lower() == col_lower]

    return data
