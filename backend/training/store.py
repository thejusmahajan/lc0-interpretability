import os
import json
import time
import uuid
import datetime
from typing import Optional, List, Dict, Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Allow overriding DATA_DIR for tests
DATA_DIR = os.getenv("CSZERO_DATA_DIR", os.path.join(ROOT_DIR, "data"))
TRAINING_DIR = os.path.join(DATA_DIR, "training")

def _ensure_dirs():
    os.makedirs(os.path.join(TRAINING_DIR, "cache"), exist_ok=True)
    os.makedirs(os.path.join(TRAINING_DIR, "jobs"), exist_ok=True)
    os.makedirs(os.path.join(TRAINING_DIR, "drills"), exist_ok=True)
    
    data_gitignore = os.path.join(DATA_DIR, ".gitignore")
    if not os.path.exists(data_gitignore):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(data_gitignore, "w", encoding="utf-8") as f:
            f.write("*\n!.gitignore\n")

class EpdCache:
    def __init__(self, name: str):
        _ensure_dirs()
        self.path = os.path.join(TRAINING_DIR, "cache", f"{name}.jsonl")
        self._data = {}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if "epd" in record:
                            self._data[record["epd"]] = record
                    except json.JSONDecodeError:
                        pass
        
    def get(self, epd: str) -> Optional[Dict[str, Any]]:
        return self._data.get(epd)

    def keys(self) -> List[str]:
        return list(self._data.keys())

    def put(self, epd: str, payload: dict):
        record = payload.copy()
        record["epd"] = epd
        self._data[epd] = record
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

def _write_json_atomic(path: str, obj):
    """Write via tmp + os.replace so concurrent readers (the 1s job poll,
    the SRS queue) never see a half-written file.

    On Windows os.replace is denied (WinError 5) while ANY other handle
    holds the target open — a concurrent reader, or antivirus scanning the
    just-written file. Those holds last milliseconds, so retry with backoff
    instead of letting a multi-hour diagnosis die on a progress write
    (which is exactly how the 2026-07-20 overnight run failed)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def _job_path(job_id: str) -> str:
    return os.path.join(TRAINING_DIR, "jobs", f"{job_id}.json")

def create_job() -> str:
    _ensure_dirs()
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "status": "queued",
        "progress": {
            "total": 0,
            "stage_a_done": 0,
            "flagged": 0,
            "stage_b_done": 0
        },
        "error": None,
        "created": datetime.datetime.utcnow().isoformat()
    }
    _write_json_atomic(_job_path(job_id), job)
    return job_id

def update_job(job_id: str, **fields):
    job = read_job(job_id)
    if not job:
        return
    for k, v in fields.items():
        if isinstance(v, dict) and k in job and isinstance(job[k], dict):
            job[k].update(v)
        else:
            job[k] = v
    _write_json_atomic(_job_path(job_id), job)

def read_job(job_id: str) -> Optional[Dict[str, Any]]:
    path = _job_path(job_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def _profiles_dir() -> str:
    return os.path.join(TRAINING_DIR, "profiles")


def _profile_version_id(created: str) -> str:
    return "profile-" + "".join(c for c in created if c.isalnum())


def save_profile(profile: dict):
    """Write the current profile AND a timestamped copy under
    training/profiles/ — diagnoses accumulate history instead of erasing it
    (T2, longitudinal trends)."""
    _ensure_dirs()
    path = os.path.join(TRAINING_DIR, "profile.json")
    _write_json_atomic(path, profile)

    os.makedirs(_profiles_dir(), exist_ok=True)
    created = profile.get("created") or datetime.datetime.utcnow().isoformat()
    version_path = os.path.join(
        _profiles_dir(), f"{_profile_version_id(created)}.json")
    _write_json_atomic(version_path, profile)


def _migrate_legacy_profile():
    """A profile.json saved before history existed enters the history once."""
    current_path = os.path.join(TRAINING_DIR, "profile.json")
    if not os.path.exists(current_path):
        return
    os.makedirs(_profiles_dir(), exist_ok=True)
    if os.listdir(_profiles_dir()):
        return
    with open(current_path, "r", encoding="utf-8") as f:
        profile = json.load(f)
    created = profile.get("created") or datetime.datetime.utcnow().isoformat()
    with open(os.path.join(_profiles_dir(),
                           f"{_profile_version_id(created)}.json"),
              "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def list_profiles() -> List[Dict[str, Any]]:
    """History metadata, oldest first: id + created + headline numbers."""
    _ensure_dirs()
    _migrate_legacy_profile()
    metas = []
    if not os.path.exists(_profiles_dir()):
        return metas
    for f_name in sorted(os.listdir(_profiles_dir())):
        if not f_name.endswith(".json"):
            continue
        try:
            with open(os.path.join(_profiles_dir(), f_name),
                      "r", encoding="utf-8") as f:
                p = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        agg = p.get("aggregates", {})
        findings = p.get("findings", [])
        confirmed = sum(1 for x in findings
                        if x.get("confirmation", {}).get("confirmed"))
        moves = p.get("moves_analyzed", 0)
        metas.append({
            "id": f_name[:-5],
            "created": p.get("created"),
            "games": p.get("games_analyzed", 0),
            "moves": moves,
            "findings": len(findings),
            "confirmed": confirmed,
            "confirmed_per_100": round(100 * confirmed / moves, 2) if moves else 0.0,
            "intuitive_blindness_rate": agg.get("intuitive_blindness_rate", 0.0),
            "attention_blindness_rate": agg.get("attention_blindness_rate", 0.0),
            "by_motif": agg.get("by_motif", {}),
            "regressions": p.get("regressions", []),
        })
    metas.sort(key=lambda m: m.get("created") or "")
    return metas

def load_profile() -> Optional[Dict[str, Any]]:
    path = os.path.join(TRAINING_DIR, "profile.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_approved_suspects(themes: List[str]) -> Dict[str, Any]:
    _ensure_dirs()
    path = os.path.join(TRAINING_DIR, "approved_suspects.json")
    data = {
        "themes": themes,
        "updated": datetime.datetime.utcnow().isoformat()
    }
    _write_json_atomic(path, data)
    return data

def load_approved_suspects() -> Dict[str, Any]:
    path = os.path.join(TRAINING_DIR, "approved_suspects.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"themes": []}

def _variant_slug(style: Optional[str], color: Optional[str]) -> Optional[str]:
    if style and color:
        return f"{style}_{color}"
    return None

def save_repertoire(repertoire: dict):
    """Persist a built repertoire per (style, color) variant, so all four
    coexist instead of clobbering one slot. Also mirrors the newest build to
    the legacy repertoire.json (kept for the no-arg loader / drill generation)."""
    _ensure_dirs()
    slug = _variant_slug(repertoire.get("style"), repertoire.get("color"))
    if slug:
        _write_json_atomic(
            os.path.join(TRAINING_DIR, f"repertoire_{slug}.json"), repertoire)
    _write_json_atomic(os.path.join(TRAINING_DIR, "repertoire.json"), repertoire)

def load_repertoire(style: Optional[str] = None,
                    color: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load a specific (style, color) variant when both are given, else the
    legacy last-built repertoire.json."""
    slug = _variant_slug(style, color)
    name = f"repertoire_{slug}.json" if slug else "repertoire.json"
    path = os.path.join(TRAINING_DIR, name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def list_repertoires() -> List[Dict[str, Any]]:
    """All saved repertoire variants, newest first. Each item is the full
    repertoire dict (they are small — a handful of recommendations each)."""
    _ensure_dirs()
    out = []
    for fname in os.listdir(TRAINING_DIR):
        if fname.startswith("repertoire_") and fname.endswith(".json"):
            try:
                with open(os.path.join(TRAINING_DIR, fname), "r",
                          encoding="utf-8") as f:
                    out.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
    out.sort(key=lambda r: r.get("created", ""), reverse=True)
    return out

def save_drill_set(drill_set: dict):
    _ensure_dirs()
    set_id = drill_set.get("id")
    if not set_id:
        raise ValueError("drill_set must have an 'id' field")
    path = os.path.join(TRAINING_DIR, "drills", f"{set_id}.json")
    _write_json_atomic(path, drill_set)

def load_drill_set(set_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(TRAINING_DIR, "drills", f"{set_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def list_drill_sets() -> List[Dict[str, Any]]:
    _ensure_dirs()
    drills_dir = os.path.join(TRAINING_DIR, "drills")
    sets = []
    if not os.path.exists(drills_dir):
        return sets
    for f_name in os.listdir(drills_dir):
        if f_name.endswith(".json"):
            path = os.path.join(drills_dir, f_name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    drills = data.get("drills", [])
                    sources = list(set(d.get("source") for d in drills if "source" in d))
                    sets.append({
                        "id": data.get("id", f_name.replace(".json", "")),
                        "created": data.get("created"),
                        "size": len(drills),
                        "sources": sources
                    })
            except Exception:
                pass
    return sets
