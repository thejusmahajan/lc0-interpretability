# After the 40-game subset (cell 6), paste this into a cell to see what the
# diagnosis actually PRODUCED — the ground truth behind the progress bars.
# If findings == 0, Stage B (Deep Confirmation) did nothing and we have a bug to fix.
from backend.training import store

prof = store.load_profile()
agg = prof.get("aggregates", {})
findings = prof.get("findings", [])

print("games_analyzed :", prof.get("games_analyzed"))
print("moves_analyzed :", prof.get("moves_analyzed"))
print("time_scramble_skipped:", prof.get("time_scramble_skipped"))
print("FINDINGS       :", len(findings), "  <-- if 0, Stage B produced nothing")
print("steer_findings :", len(prof.get("steer_findings", [])))
print("by_opening ecos:", len(agg.get("by_opening", {})))
print("by_phase       :", agg.get("by_phase"))
print("by_clock       :", agg.get("by_clock"))

# severity + confirmation breakdown of findings (did Stage B actually confirm?)
from collections import Counter
sev = Counter(f.get("severity") for f in findings)
conf = Counter(bool(f.get("confirmation", {}).get("confirmed")) for f in findings)
print("severity counts:", dict(sev))
print("confirmed counts:", dict(conf), " <-- Stage B sets confirmation; all-False/empty = B skipped")
if findings:
    f0 = findings[0]
    print("sample finding keys:", sorted(f0.keys()))
    print("sample confirmation:", f0.get("confirmation"))
