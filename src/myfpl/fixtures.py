#!/usr/bin/env python3
"""Fetch and parse FPL fixtures into a fixtures_map.

This module centralizes downloading, saving and mapping of fixtures so other
modules (like player_history) can reuse the logic.
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List
import click

FPL_BASE = "https://fantasy.premierleague.com/api"


def parse_kickoff(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        return iso


def fetch_json(url: str, retries: int = 2, backoff: float = 0.3) -> List[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "myfpl-fetcher/1.0"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            raise


def build_fixtures_map(fixtures: List[dict]) -> Dict[int, dict]:
    """Return a mapping fixture_id -> dict with event, kickoff_time and teams."""
    m = {}
    for fx in fixtures or []:
        m[fx.get("id")] = {
            "event": fx.get("event"),
            "kickoff_time": parse_kickoff(fx.get("kickoff_time")) if fx.get("kickoff_time") else None,
            "team_h": fx.get("team_h") if "team_h" in fx else fx.get("team_h"),
            "team_a": fx.get("team_a") if "team_a" in fx else fx.get("team_a"),
        }
    return m


def get_fixtures_map(output_dir: str, no_fetch: bool = False) -> Dict[int, dict]:
    """Return fixtures_map. If no_fetch is False, fetch from API and save to output_dir.

    If no_fetch is True, try to load an existing `fixtures.json` from output_dir. If
    the file isn't present, return an empty dict.
    """
    fixtures_path = os.path.join(output_dir, "fixtures.json")
    if no_fetch:
        if os.path.exists(fixtures_path):
            try:
                with open(fixtures_path, "r", encoding="utf-8") as f:
                    fixtures = json.load(f)
                return build_fixtures_map(fixtures)
            except Exception:
                return {}
        return {}

    # fetch from API and save
    fixtures = fetch_json(f"{FPL_BASE}/fixtures/")
    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(fixtures_path, "w", encoding="utf-8") as f:
            json.dump(fixtures, f, ensure_ascii=False, indent=2)
    except Exception:
        # saving is best-effort; still return the map
        pass
    return build_fixtures_map(fixtures)


@click.command()
@click.option("--output", "out_path", default="./fixtures_map.json", show_default=True,
              type=click.Path(file_okay=True, dir_okay=False, writable=True),
              help="Path (directory+filename) where the parsed fixtures_map JSON will be written.\n"
                   "The directory containing this path is also used to read/save the raw fixtures.json when fetching.")
@click.option("--no-fetch", is_flag=True, default=False,
              help="Do not fetch fixtures from the network; read local fixtures.json from the output file's directory if present")
def cli(out_path: str, no_fetch: bool):
    """Fetch/parse fixtures and write the parsed fixtures_map to OUT.

    The parsed fixtures_map maps fixture id -> {event, kickoff_time, team_h, team_a}.
    The raw `fixtures.json` will be saved (or read) in the same directory as OUT.
    """
    output_dir = os.path.dirname(out_path) or '.'

    try:
        fmap = get_fixtures_map(output_dir, no_fetch=no_fetch)
    except Exception as e:
        click.echo(f"Failed to obtain fixtures: {e}", err=True)
        raise SystemExit(2)

    if not fmap:
        click.echo("No fixtures available; writing empty map")

    try:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fmap, f, ensure_ascii=False, indent=2)
        click.echo(f"Wrote parsed fixtures_map to {out_path}")
    except Exception as e:
        click.echo(f"Failed to write fixtures_map to {out_path}: {e}", err=True)
        raise SystemExit(3)


if __name__ == "__main__":
    cli()
