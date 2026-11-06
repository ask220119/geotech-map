#!/usr/bin/env python3
"""Map of Geotechnics — pipeline runner.

  python run.py all            fetch from OpenAlex + Semantic Scholar, then build everything
  python run.py build          rebuild from data/works.jsonl (no download)
  python run.py demo           synthetic corpus + build (offline test)
  python run.py <step> ...     any of: fetch embed graph cluster layout borders names export
"""
import sys
import time

from geomap import borders, cluster, demo, embed, export, fetch, graph, layout, naming
from geomap.common import load_config

STEPS = {"fetch": fetch.run, "embed": embed.run, "graph": graph.run, "cluster": cluster.run, "layout": layout.run,
         "borders": borders.run, "names": naming.run, "export": export.run}
BUILD = ["graph", "cluster", "layout", "borders", "names", "export"]


def main(argv):
    if not argv:
        print(__doc__)
        return
    cfg = load_config()
    if argv == ["all"]:
        steps = ["fetch", "embed"] + BUILD
    elif argv == ["build"]:
        steps = BUILD
    elif argv == ["demo"]:
        demo.run()
        steps = BUILD
    else:
        steps = argv
    for s in steps:
        if s not in STEPS:
            sys.exit(f"unknown step '{s}'. Choose from: {', '.join(STEPS)}")
        t = time.time()
        STEPS[s](cfg)
        print(f"   ({s}: {time.time() - t:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1:])
