#!/usr/bin/env python3
"""Map of Geotechnics — pipeline runner.

  python run.py all            fetch OpenAlex + ISSMGE + Semantic Scholar, then build everything
  python run.py build          rebuild from data/works.jsonl (no download)
  python run.py demo           synthetic corpus + build (offline test)
  python run.py <step> ...     any of: fetch issmge embed embed_local graph cluster layout overlay borders names export
"""
import sys
import time

from geomap import (borders, cluster, demo, embed, embed_local, export, fetch, graph, issmge, layout,
                    naming, overlay)
from geomap.common import load_config

STEPS = {"fetch": fetch.run, "issmge": issmge.run, "embed": embed.run, "embed_local": embed_local.run,
         "graph": graph.run, "cluster": cluster.run, "layout": layout.run, "overlay": overlay.run,
         "borders": borders.run, "names": naming.run, "export": export.run}
BUILD = ["graph", "cluster", "layout", "overlay", "borders", "names", "export"]


def main(argv):
    if not argv:
        print(__doc__)
        return
    cfg = load_config()
    if argv == ["all"]:
        steps = ["fetch", "issmge", "embed", "embed_local"] + BUILD
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
