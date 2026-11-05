"""Shared helpers: paths, config, JSONL I/O."""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("GEOMAP_DATA", ROOT / "data"))
OUT = Path(os.environ.get("GEOMAP_OUT", ROOT / "web" / "data"))


def load_config(path: str | os.PathLike | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def short_id(openalex_id: str) -> str:
    """'https://openalex.org/W123' -> 'W123'"""
    return openalex_id.rsplit("/", 1)[-1] if openalex_id else openalex_id


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj, indent=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))


def log(step: str, *msg):
    print(f"[{step}]", *msg, flush=True)
