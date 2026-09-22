"""
Source-text acquisition — leader-controlled, so a transcription always has something to verify against.

Acquisition is deliberately NOT delegated. `provenance_check.py` only means anything if the text a
transcription is checked against was fetched independently of whoever wrote the transcription; a
worker that supplies both sides of the comparison can satisfy the gate by supplying a matching pair.

Every entry below is public domain in the US (published <= 1930; the term is 95 years from
publication, so 1930 expired at the end of 2025). `docs/public_domain_chess_library.md` is the
approved shelf and the exclusion list.

Run: `python -m backend.training.acquire_source_texts [--dry-run]`
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

SOURCE_TEXT_DIR = os.path.join("scratch", "source_texts")
MANIFEST_PATH = os.path.join(SOURCE_TEXT_DIR, "acquisition_manifest.json")
UA = {"User-Agent": "chess_speak_out_loud research corpus (public-domain texts)"}
REQUEST_PAUSE = 1.5


@dataclass(frozen=True)
class Target:
    """One public-domain work we want the full text of."""

    slug: str
    author: str
    title: str
    year: int
    authority: str          # world_champion | grandmaster | reputable_published
    search: str             # archive.org query fragment
    note: str = ""

    def __post_init__(self) -> None:
        if self.year > 1930:
            raise ValueError(f"{self.slug}: {self.year} is not public domain in 2026")


TARGETS: List[Target] = [
    # --- World champions annotating their own games: the highest-authority material there is.
    Target("alekhine_my_best_games_1908_1923_1927", "Alekhine, Alexander",
           "My Best Games of Chess 1908-1923", 1927, "world_champion",
           'title:("my best games of chess")',
           "Alekhine on Alekhine. The 1924-1937 volume (1939) is NOT public domain."),
    Target("lasker_common_sense_in_chess_1896", "Lasker, Emanuel",
           "Common Sense in Chess", 1896, "world_champion",
           'title:("common sense in chess")'),
    Target("lasker_manual_of_chess_1927", "Lasker, Emanuel",
           "Lasker's Manual of Chess", 1927, "world_champion",
           'title:("manual of chess") AND creator:(lasker)'),
    Target("steinitz_modern_chess_instructor_1889", "Steinitz, Wilhelm",
           "The Modern Chess Instructor", 1889, "world_champion",
           'title:("modern chess instructor")'),

    # --- Elite contemporaries and theoreticians.
    Target("tarrasch_dreihundert_schachpartien_1895", "Tarrasch, Siegbert",
           "Dreihundert Schachpartien", 1895, "grandmaster",
           'title:("dreihundert schachpartien")', "German; translate per task rules."),
    Target("nimzowitsch_mein_system_1925", "Nimzowitsch, Aron",
           "Mein System", 1925, "grandmaster",
           'title:("mein system") AND creator:(nimzowitsch)', "German original is the PD text."),
    Target("reti_modern_ideas_in_chess_1922", "Reti, Richard",
           "Modern Ideas in Chess", 1922, "grandmaster",
           'title:("modern ideas in chess")'),
    Target("marshall_chess_swindles_1914", "Marshall, Frank J.",
           "Marshall's Chess Swindles", 1914, "grandmaster",
           'title:("chess swindles")'),
    Target("znosko_borovsky_middle_game_1922", "Znosko-Borovsky, Eugene",
           "The Middle Game in Chess", 1922, "reputable_published",
           'title:("middle game in chess")',
           "1922 ed. only. His 1936/1940 titles are NOT public domain."),

    # --- Morphy annotated by strong contemporaries.
    Target("lowenthal_morphys_games_1860", "Lowenthal, Johann",
           "Morphy's Games of Chess", 1860, "reputable_published",
           'title:("morphy\'s games of chess")'),
    Target("sergeant_morphys_games_1916", "Sergeant, Philip W.",
           "Morphy's Games of Chess", 1916, "reputable_published",
           'title:("morphy gleanings") OR title:("morphy\'s games of chess")'),

    # --- Tournament books: annotations by the elite of the day.
    Target("new_york_1924", "Alekhine, Alexander",
           "New York 1924 tournament book", 1925, "world_champion",
           'title:("new york 1924")', "Alekhine annotated the whole event."),
    Target("st_petersburg_1909", "Lasker, Emanuel",
           "St Petersburg 1909 tournament book", 1910, "world_champion",
           'title:("st petersburg 1909") OR title:("internationale schachturnier")'),
]


def _get(url: str, timeout: int = 120) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def search_archive(query: str, rows: int = 12) -> List[Dict[str, Any]]:
    """Archive.org items matching `query`, newest metadata first."""
    full = f"({query}) AND mediatype:texts"
    url = (
        "https://archive.org/advancedsearch.php?q="
        + urllib.parse.quote(full)
        + "&fl[]=identifier&fl[]=title&fl[]=year&fl[]=creator"
        + f"&rows={rows}&output=json"
    )
    try:
        return json.loads(_get(url))["response"]["docs"]
    except Exception:
        return []


def find_full_text(identifier: str) -> Optional[str]:
    """The name of a downloadable plain-text file for an item, if it is not lending-restricted."""
    try:
        meta = json.loads(_get(f"https://archive.org/metadata/{identifier}"))
    except Exception:
        return None
    if meta.get("metadata", {}).get("access-restricted-item") == "true":
        return None
    texts = [f["name"] for f in meta.get("files", []) if f["name"].endswith(".txt")]
    # Prefer the OCR sidecar over READMEs and metadata dumps.
    texts.sort(key=lambda n: (0 if n.endswith("_djvu.txt") else 1, len(n)))
    return texts[0] if texts else None


_CHESS_MARKERS = ("chess", "pawn", "bishop", "knight", "queen", "castl")

# Modern publishers and post-1930 copyright notices. A title search alone is NOT enough: searching
# for "my best games of chess" returned Vishy Anand & John Nunn (Gambit, 1998), and "my chess career"
# returned the Dover 1966 edition carrying an Irving Chernev introduction — both copyrighted, and
# Chernev is on our own exclusion list. Both were caught only by reading the front matter afterwards.
_MODERN_PUBLISHER_RE = re.compile(
    r"(gambit publications|dover publications|everyman chess|batsford|quality chess|new in chess|"
    r"chessbase|russell enterprises|mcfarland|pergamon|routledge|chernev)",
    re.IGNORECASE,
)
_MODERN_COPYRIGHT_RE = re.compile(
    r"copyright\s*(?:©|\(c\)|�)?\s*,?\s*(19[3-9]\d|20[0-2]\d)", re.IGNORECASE
)


def screen_copyright(text: str, max_year: int = 1930) -> Optional[str]:
    """Reject reason if the front matter shows a modern edition, else None."""
    front = text[:20000]
    publisher = _MODERN_PUBLISHER_RE.search(front)
    if publisher:
        return f"modern_publisher:{publisher.group(1).lower()}"
    for year in _MODERN_COPYRIGHT_RE.findall(front):
        if int(year) > max_year:
            return f"modern_copyright:{year}"
    return None


def looks_like_chess_text(text: str) -> bool:
    """Cheap sanity gate — a mis-hit search should not silently become a source text."""
    sample = text[:200000].lower()
    hits = sum(1 for marker in _CHESS_MARKERS if sample.count(marker) >= 5)
    return len(text) > 20000 and hits >= 4


def acquire(target: Target, dry_run: bool = False) -> Dict[str, Any]:
    """Locate, validate and download one target. Never raises."""
    result: Dict[str, Any] = {
        "slug": target.slug, "author": target.author, "title": target.title,
        "year": target.year, "authority": target.authority, "note": target.note,
        "status": "not_found", "identifier": None, "url": None, "path": None, "chars": 0,
    }

    for doc in search_archive(target.search):
        identifier = doc.get("identifier")
        if not identifier:
            continue
        time.sleep(REQUEST_PAUSE)
        name = find_full_text(identifier)
        if not name:
            continue

        url = f"https://archive.org/download/{identifier}/{urllib.parse.quote(name)}"
        result.update(identifier=identifier, url=url,
                      archive_title=str(doc.get("title"))[:120], archive_year=doc.get("year"))
        if dry_run:
            result["status"] = "found"
            return result

        try:
            time.sleep(REQUEST_PAUSE)
            text = _get(url, timeout=300).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - network is expected to be flaky
            result["status"] = f"download_failed: {type(exc).__name__}"
            continue

        if not looks_like_chess_text(text):
            result["status"] = "rejected_not_chess_text"
            continue

        reason = screen_copyright(text)
        if reason:
            result["status"] = f"rejected_{reason}"
            continue

        os.makedirs(SOURCE_TEXT_DIR, exist_ok=True)
        path = os.path.join(SOURCE_TEXT_DIR, f"{target.slug}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        result.update(status="ok", path=path.replace("\\", "/"), chars=len(text))
        return result

    return result


def main(dry_run: bool = False) -> List[Dict[str, Any]]:
    results = [acquire(t, dry_run=dry_run) for t in TARGETS]
    if not dry_run:
        os.makedirs(SOURCE_TEXT_DIR, exist_ok=True)
        with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, ensure_ascii=False)
    for r in results:
        print(f"{r['status']:28} {r['slug']:44} {r['chars'] or '':>8} {r.get('identifier') or ''}")
    return results


if __name__ == "__main__":  # pragma: no cover - operator entry point
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    main(dry_run=parser.parse_args().dry_run)
