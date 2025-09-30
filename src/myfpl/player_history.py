#!/usr/bin/env python3
"""Fetch per-gameweek player histories from the public FPL API.

This script uses the functions in `player_data.py` to resolve player queries
against a local `bootstrap-static.json`, then fetches element-summary and
fixtures from the public FPL API and writes per-player JSON files and a
combined CSV with a row per gameweek performance.

Notes / limitations:
- The public FPL API does not provide per-goal timestamps (minute of goal)
  in its element-summary or fixtures endpoints. It provides per-match counts
  (goals_scored, assists, saves, etc.) and fixture kickoff_time which can be
  used to associate a game to a datetime, but not the exact timestamp of
  each scoring event.
"""
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List

import click

from player_data import load_bootstrap, find_players, sanitize_filename


FPL_BASE = "https://fantasy.premierleague.com/api"


def fetch_json(url: str, retries: int = 2, backoff: float = 0.3) -> Dict:
    req = urllib.request.Request(url, headers={"User-Agent": "myfpl-fetcher/1.0"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # 404 or 5xx - no point retrying some errors
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


def save_json(obj: Dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def parse_kickoff(iso: str) -> str:
    try:
        # keep original timezone info if present
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        return iso


@click.command()
@click.option("--player", required=True, help="Player name (web name or full name)")
@click.option("--bootstrap", "bootstrap_path", default="bootstrap-static.json", show_default=True,
              help="Path to bootstrap-static.json")
@click.option("--output-dir", "output_dir", default="./player_histories", show_default=True,
              type=click.Path(file_okay=False, dir_okay=True, writable=True),
              help="Directory to write outputs to")
@click.option("--no-fetch", is_flag=True, default=False,
              help="Do not fetch data from the network; only use local bootstrap data")
def cli(player: str, bootstrap_path: str, output_dir: str, no_fetch: bool):
    """Fetch per-gameweek histories for PLAYER and write JSON + CSV into OUTPUT_DIR."""

    if not os.path.exists(bootstrap_path):
        click.echo(f"bootstrap file not found: {bootstrap_path}", err=True)
        raise SystemExit(2)

    try:
        boot = load_bootstrap(bootstrap_path)
    except Exception as e:
        click.echo(f"Failed to load bootstrap file: {e}", err=True)
        raise SystemExit(3)

    matches = find_players(boot, player)
    if not matches:
        click.echo(f"Player not found for query: '{player}'", err=True)
        raise SystemExit(1)

    os.makedirs(output_dir, exist_ok=True)

    # optionally fetch fixtures to map fixture -> kickoff_time and event (gameweek)
    fixtures_map = {}
    fixtures_path = os.path.join(output_dir, "fixtures.json")
    if not no_fetch:
        click.echo("Fetching fixtures from FPL API...")
        fixtures = fetch_json(f"{FPL_BASE}/fixtures/")
        save_json(fixtures, fixtures_path)
        for fx in fixtures:
            fixtures_map[fx.get("id")] = {
                "event": fx.get("event"),
                "kickoff_time": parse_kickoff(fx.get("kickoff_time")) if fx.get("kickoff_time") else None,
                "team_homes": (fx.get("team_h") if "team_h" in fx else fx.get("team_h")),
                "team_aways": (fx.get("team_a") if "team_a" in fx else fx.get("team_a")),
            }
        click.echo(f"Fetched {len(fixtures)} fixtures; saved to {fixtures_path}")
    else:
        click.echo("Skipping network fetch of fixtures ( --no-fetch ).")

    combined_rows: List[Dict] = []

    for el in matches:
        pid = el.get("id")
        pname = ((el.get("first_name") or "") + " " + (el.get("second_name") or "")).strip() or el.get("web_name")
        filename_base = sanitize_filename(pname or f"player_{pid}")

        if not no_fetch:
            click.echo(f"Fetching element-summary for {pname} (id={pid})...")
            summary = fetch_json(f"{FPL_BASE}/element-summary/{pid}/")
            player_json_path = os.path.join(output_dir, f"element_{pid}_summary.json")
            save_json(summary, player_json_path)
        else:
            click.echo(f"Skipping element-summary fetch for {pname} (id={pid})")
            summary = {"history": []}

        # history entries are per-match / per-gameweek. We'll merge available fields
        history = summary.get("history", []) or []
        for h in history:
            # attach player metadata
            row = dict(h)  # shallow copy
            row.setdefault("player_id", pid)
            row.setdefault("player_name", pname)

            # map fixture -> kickoff_time + event id when available
            fx_id = h.get("fixture")
            if fx_id and fx_id in fixtures_map:
                fx = fixtures_map[fx_id]
                row["fixture_event"] = fx.get("event")
                row["fixture_kickoff_time"] = fx.get("kickoff_time")
            else:
                # element-summary may contain a 'round' or 'event' field already
                row["fixture_event"] = h.get("round") or h.get("event") or h.get("round_id")
                row["fixture_kickoff_time"] = None

            combined_rows.append(row)

        # write per-player CSV as well
        if history:
            keys = sorted({k for d in history for k in d.keys()})
            # include our extra columns
            extra = ["player_id", "player_name", "fixture_event", "fixture_kickoff_time"]
            out_keys = extra + [k for k in keys if k not in extra]
            csv_path = os.path.join(output_dir, f"{filename_base}_{pid}_history.csv")
            with open(csv_path, "w", newline='', encoding="utf-8") as csvf:
                w = csv.DictWriter(csvf, fieldnames=out_keys, extrasaction="ignore")
                w.writeheader()
                for r in combined_rows:
                    if r.get("player_id") == pid:
                        w.writerow({k: r.get(k) for k in out_keys})
            click.echo(f"Wrote history CSV for {pname} -> {csv_path}")
        else:
            click.echo(f"No per-gameweek history available for {pname} (id={pid})")

    # write combined CSV for all players
    if combined_rows:
        keys = sorted({k for d in combined_rows for k in d.keys()})
        extra = ["player_id", "player_name", "fixture_event", "fixture_kickoff_time"]
        out_keys = extra + [k for k in keys if k not in extra]
        combined_path = os.path.join(output_dir, "players_history_combined.csv")
        with open(combined_path, "w", newline='', encoding="utf-8") as csvf:
            w = csv.DictWriter(csvf, fieldnames=out_keys, extrasaction="ignore")
            w.writeheader()
            for r in combined_rows:
                w.writerow({k: r.get(k) for k in out_keys})
        click.echo(f"Wrote combined history CSV -> {combined_path}")
    else:
        click.echo("No per-gameweek rows collected; combined CSV not written.")


if __name__ == "__main__":
    cli()
