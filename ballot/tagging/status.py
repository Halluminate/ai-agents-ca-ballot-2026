"""Progress of one shard: python3 status.py NN"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
shard = sys.argv[1].zfill(2)
ids = (HERE / "shards" / f"shard-{shard}.txt").read_text().split()
out = HERE / "out" / f"shard-{shard}.jsonl"
done = [json.loads(line)["id"] for line in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
stray = sorted(set(done) - set(ids))
dupes = sorted({i for i in done if done.count(i) > 1})
todo = [i for i in ids if i not in set(done)]
print(f"shard {shard}: {len(set(done) & set(ids))}/{len(ids)} done, {len(todo)} to go")
if todo:
    print("next, in order:", " ".join(todo[:8]))
else:
    print("every id is done; write out/shard-%s.report.md if you haven't" % shard)
if stray or dupes:
    print("PROBLEM: ids not in this shard:", stray, "duplicates:", dupes)
