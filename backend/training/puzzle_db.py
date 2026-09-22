import sqlite3
import os
import random
from typing import List, Dict, Tuple, Optional, Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.getenv("CSZERO_PUZZLE_DB", os.path.join(ROOT_DIR, "data", "puzzles", "puzzles.sqlite"))

def _get_connection():
    return sqlite3.connect(DB_PATH)

def motif_profile(opening_tag: str) -> Dict[str, float]:
    """Returns {theme: freq} for a given opening_tag."""
    if not os.path.exists(DB_PATH):
        return {}
        
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT theme, n FROM opening_motifs WHERE opening_tag = ?", (opening_tag,))
        rows = cur.fetchall()
        
    if not rows:
        return {}
        
    total = sum(n for _, n in rows)
    if total == 0:
        return {}
        
    return {theme: n / total for theme, n in rows}

def sample_puzzles(themes: Optional[List[str]], opening_tags: Optional[List[str]], rating_range: Tuple[int, int], limit: int) -> List[Dict[str, Any]]:
    """Sample puzzles matching criteria."""
    if not os.path.exists(DB_PATH):
        return []
        
    if themes is None:
        themes = []

    min_rating, max_rating = rating_range
    query = "SELECT id, fen, moves, rating, popularity, themes, opening_tags FROM puzzles WHERE rating >= ? AND rating <= ?"
    params = [min_rating, max_rating]
    
    theme_conditions = []
    for theme in themes:
        # SQLite LIKE '% theme %' trick or just '%theme%'
        theme_conditions.append("themes LIKE ?")
        params.append(f"%{theme}%")
        
    if theme_conditions:
        query += " AND (" + " OR ".join(theme_conditions) + ")"
        
    if opening_tags:
        tag_conditions = []
        for tag in opening_tags:
            tag_conditions.append("opening_tags LIKE ?")
            params.append(f"%{tag}%")
        if tag_conditions:
            query += " AND (" + " OR ".join(tag_conditions) + ")"
            
    query += f" ORDER BY RANDOM() LIMIT {limit}"
    
    with _get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        
    return [dict(row) for row in rows]

def opening_tags_ranked(theme: str, min_n: int = 200) -> List[Tuple[str, float, int]]:
    """Returns [(tag, freq, n)] where n >= min_n, sorted by freq desc.
    min_n=200 suits common themes; rare themes (sacrifice family) need a
    lower floor on the 300k-row sample or the candidate pool starves."""
    if not os.path.exists(DB_PATH):
        return []

    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT opening_tag, SUM(n) FROM opening_motifs GROUP BY opening_tag")
        totals = dict(cur.fetchall())

        cur.execute("SELECT opening_tag, n FROM opening_motifs WHERE theme = ? AND n >= ?", (theme, min_n))
        rows = cur.fetchall()
        
    result = []
    for tag, n in rows:
        total = totals.get(tag, 1)
        freq = n / total
        result.append((tag, freq, n))
        
    result.sort(key=lambda x: -x[1])
    return result
