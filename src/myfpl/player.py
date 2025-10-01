#!/usr/bin/env python3
"""Combined player metadata + per-gameweek history extractor for FPL bootstrap + API."""

import json
import os
import re
import time
import unicodedata
import urllib.request
import urllib.error
from difflib import get_close_matches
from datetime import datetime
from typing import Dict, List

import click
from myfpl.fixtures import get_fixtures_map, build_fixtures_map

FPL_BASE = "https://fantasy.premierleague.com/api"


def sanitize_filename(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


def load_bootstrap(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_json(url: str, retries: int = 2, backoff: float = 0.3) -> Dict:
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


def parse_kickoff(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        return iso


def build_position_map(bootstrap: dict) -> dict:
    pos_map = {}
    for et in bootstrap.get("element_types", []):
        pos_map[et["id"]] = et.get("singular_name") or et.get("singular_name_short")
    return pos_map


def build_team_map(bootstrap: dict) -> dict:
    tm = {}
    for t in bootstrap.get("teams", []):
        tm[t["id"]] = {
            "id": t.get("id"),
            "name": t.get("name"),
            "short_name": t.get("short_name"),
            "code": t.get("code"),
        }
    return tm


def find_players(bootstrap: dict, query: str) -> list:
    q = query.strip().lower()
    elements = bootstrap.get("elements", [])
    name_to_elems = {}
    candidates = []
    for el in elements:
        web = (el.get("web_name") or "").strip()
        full = (
            (el.get("first_name") or "") + " " + (el.get("second_name") or "")
        ).strip()
        alt = (el.get("second_name") or "").strip()
        first = (el.get("first_name") or "").strip()
        for nm in {web, full, alt, first}:
            if not nm:
                continue
            key = nm.lower()
            name_to_elems.setdefault(key, []).append(el)
            candidates.append(key)
    if q in name_to_elems:
        return list({el["id"]: el for el in name_to_elems[q]}.values())
    substring_keys = [name for name in candidates if q in name]
    if substring_keys:
        seen = {}
        for key in substring_keys:
            for el in name_to_elems.get(key, []):
                seen[el["id"]] = el
        return list(seen.values())
    close = get_close_matches(q, candidates, n=1, cutoff=0.6)
    if close:
        return list({el["id"]: el for el in name_to_elems[close[0]]}.values())
    return []


def _extract_gameweek_stats(
    history: List[dict], fixtures_map: Dict[int, dict] = None
) -> List[dict]:
    out = []
    fixtures_map = fixtures_map or {}
    for h in history or []:
        ev = h.get("round") or h.get("event")
        if h.get("fixture") and fixtures_map and h.get("fixture") in fixtures_map:
            ev = fixtures_map[h.get("fixture")].get("event")
        total_score = (
            h.get("total_points")
            or h.get("event_points")
            or h.get("points")
            or h.get("total")
            or 0
        )
        item = {
            "event": ev,
            "goals": h.get("goals_scored") or 0,
            "assists": h.get("assists") or 0,
            "yellow_cards": h.get("yellow_cards") or 0,
            "red_cards": h.get("red_cards") or 0,
            "goals_conceded": h.get("goals_conceded") or 0,
            "total_score": total_score,
        }
        out.append(item)
    return out


@click.command()
@click.option("--player", required=True, help="Player name (web name or full name)")
@click.option(
    "--bootstrap",
    "bootstrap_path",
    default="bootstrap-static.json",
    show_default=True,
    help="Path to bootstrap-static.json",
)
@click.option(
    "--output-dir",
    "output_dir",
    default="./players",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True, writable=True),
    help="Directory to write outputs to",
)
@click.option(
    "--fixtures",
    "fixtures_path",
    default=None,
    show_default=True,
    type=click.Path(file_okay=True, dir_okay=False, readable=True),
    help="Path to a fixtures.json file to use instead of fetching (overrides --no-fetch)",
)
@click.option(
    "--no-fetch",
    is_flag=True,
    default=False,
    help="Do not fetch element-summary/fixtures from network; only use bootstrap",
)
@click.option(
    "--keep-summaries",
    is_flag=True,
    default=False,
    help="Do not remove downloaded element_{id}_summary.json files (useful for debugging)",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Print extra debug information about network fetches and parsed data",
)
def cli(
    player: str,
    bootstrap_path: str,
    output_dir: str,
    fixtures_path: str,
    no_fetch: bool,
    keep_summaries: bool,
    verbose: bool,
):
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

    # obtain fixtures map (may fetch and save fixtures.json)
    fixtures_map = {}
    if fixtures_path:
        try:
            with open(fixtures_path, "r", encoding="utf-8") as f:
                fixtures = json.load(f)
            # Accept either a raw fixtures list (from the FPL API) or a pre-built fixtures_map
            if isinstance(fixtures, dict):
                # assume it's already a fixtures_map: fixture_id -> {event,..}
                fixtures_map = (
                    {int(k): v for k, v in fixtures.items()} if fixtures else {}
                )
                click.echo(
                    f"Loaded pre-parsed fixtures_map with {len(fixtures_map)} entries from {fixtures_path}"
                )
            else:
                # assume raw list
                fixtures_map = build_fixtures_map(fixtures)
                click.echo(
                    f"Loaded {len(fixtures_map)} fixtures from raw fixtures file {fixtures_path}"
                )
        except Exception as e:
            click.echo(
                f"Warning: failed to load fixtures from {fixtures_path}: {e}", err=True
            )
            fixtures_map = {}
    else:
        fixtures_map = get_fixtures_map(output_dir, no_fetch=no_fetch)
        if fixtures_map:
            click.echo(f"Loaded {len(fixtures_map)} fixtures")
        else:
            if no_fetch:
                click.echo(
                    "No local fixtures.json found; continuing without fixture mapping"
                )
            else:
                click.echo(
                    "Failed to fetch fixtures; continuing without fixture mapping"
                )

    pos_map = build_position_map(boot)
    team_map = build_team_map(boot)

    written = []
    for el in matches:
        pid = el.get("id")
        full_name = (
            (el.get("first_name") or "") + " " + (el.get("second_name") or "")
        ).strip() or el.get("web_name")
        position = pos_map.get(el.get("element_type"), str(el.get("element_type")))
        now_cost_raw = el.get("now_cost")
        try:
            cost = float(now_cost_raw) / 10.0 if now_cost_raw is not None else None
        except Exception:
            cost = now_cost_raw
        total_points = el.get("total_points")

        team_info = team_map.get(el.get("team")) or {"id": el.get("team")}

        # fetch element-summary for per-gameweek history unless disabled
        history_raw = []
        summary_file = None
        if not no_fetch:
            url = f"{FPL_BASE}/element-summary/{pid}/"
            try:
                if verbose:
                    click.echo(f"Fetching element-summary from {url}")
                summary = fetch_json(url)
                # Some responses include `history` (current season) and/or `history_past`.
                # Combine both so we don't lose data when one is empty.
                hist_cur = summary.get("history") or []
                hist_past = summary.get("history_past") or []
                history_raw = list(hist_cur) + list(hist_past)
                # save raw element-summary to a temp file which we'll remove after use
                summary_file = os.path.join(output_dir, f"element_{pid}_summary.json")
                try:
                    with open(summary_file, "w", encoding="utf-8") as f:
                        json.dump(summary, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    # non-fatal if we cannot save the summary
                    if verbose:
                        click.echo(
                            f"Warning: failed to write element summary to {summary_file}: {e}",
                            err=True,
                        )
                if verbose:
                    click.echo(
                        f"Fetched element-summary for id={pid}, history entries: {len(history_raw)} (history: {len(hist_cur)}, history_past: {len(hist_past)})"
                    )
                    if not history_raw:
                        click.echo(
                            f"Debug: element-summary response keys: {list(summary.keys())}"
                        )
            except Exception as e:
                click.echo(
                    f"Warning: failed to fetch element-summary for id={pid}: {e}",
                    err=True,
                )

        history = _extract_gameweek_stats(history_raw, fixtures_map)

        out = {
            "id": pid,
            "name": full_name or el.get("web_name"),
            "web_name": el.get("web_name"),
            "position": position,
            "cost_million": cost,
            "total_points": total_points,
            "status": el.get("status"),
            "team": team_info,
            "history": history,
        }

        base = sanitize_filename(full_name or el.get("web_name") or f"player_{pid}")
        filename = f"{base}_{pid}.json" if len(matches) > 1 else f"{base}.json"
        out_path = os.path.join(output_dir, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        written.append(out_path)
        click.echo(f"Wrote {out_path}")

        # remove temporary element summary file if we created one (unless user asked to keep)
        if summary_file and not keep_summaries:
            try:
                if os.path.exists(summary_file):
                    os.remove(summary_file)
            except Exception as e:
                click.echo(
                    f"Warning: failed to remove temporary file {summary_file}: {e}",
                    err=True,
                )

    click.echo(f"Wrote {len(written)} player file(s).")


if __name__ == "__main__":
    cli()

