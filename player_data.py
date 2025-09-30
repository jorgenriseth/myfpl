#!/usr/bin/env python3
"""Extract a player's basic info from a Fantasy FPL `bootstrap-static.json` file.

This script uses click and options. Example:
    python player_data.py --player "Raya" --bootstrap bootstrap-static.json --output-dir ./players

The output is a JSON file named after the player (lowercase, spaces -> underscores,
diacritics removed) containing name, position, cost, total_points and expanded stats.
"""
import json
import os
import re
import unicodedata
from difflib import get_close_matches
import click


def sanitize_filename(name: str) -> str:
    # Normalize unicode (decompose characters) and remove diacritics
    s = unicodedata.normalize("NFKD", name)
    # Remove combining marks (accents)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"\s+", "_", s)
    # Keep only ascii letters, numbers and underscores
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


def load_bootstrap(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_position_map(bootstrap: dict) -> dict:
    # map element_type id -> readable position
    pos_map = {}
    for et in bootstrap.get("element_types", []):
        # prefer singular_name (e.g. 'Goalkeeper')
        pos_map[et["id"]] = et.get("singular_name") or et.get("singular_name_short")
    return pos_map


def build_team_map(bootstrap: dict) -> dict:
    """Return a mapping team_id -> dict with id, name, short_name, code"""
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
    """Return a list of element dicts matching the query.

    Matching strategy (descending priority):
      - exact match against web_name, full name, first or second name
      - substring matches (any candidate containing query)
      - fuzzy closest match (1-best)

    Returns an empty list when nothing matches.
    """
    q = query.strip().lower()
    elements = bootstrap.get("elements", [])

    # prepare a mapping from candidate name -> list of elements
    name_to_elems = {}
    candidates = []
    for el in elements:
        web = (el.get("web_name") or "").strip()
        full = ((el.get("first_name") or "") + " " + (el.get("second_name") or "")).strip()
        alt = (el.get("second_name") or "").strip()
        first = (el.get("first_name") or "").strip()
        for nm in {web, full, alt, first}:
            if not nm:
                continue
            key = nm.lower()
            name_to_elems.setdefault(key, []).append(el)
            candidates.append(key)

    # 1) exact match
    if q in name_to_elems:
        # return a copy to avoid external mutation
        return list({el['id']: el for el in name_to_elems[q]}.values())

    # 2) substring matches (contains) - collect all distinct elements
    substring_keys = [name for name in candidates if q in name]
    if substring_keys:
        seen = {}
        for key in substring_keys:
            for el in name_to_elems.get(key, []):
                seen[el['id']] = el
        return list(seen.values())

    # 3) fuzzy closest match (single key)
    close = get_close_matches(q, candidates, n=1, cutoff=0.6)
    if close:
        return list({el['id']: el for el in name_to_elems[close[0]]}.values())

    return []


@click.command()
@click.option('--player', required=True, help='Player name (web name or full name)')
@click.option('--bootstrap', 'bootstrap_path', default='bootstrap-static.json', show_default=True,
              help='Path to bootstrap-static.json')
@click.option('--output-dir', 'output_dir', default='.', show_default=True,
              type=click.Path(file_okay=False, dir_okay=True, writable=True),
              help='Directory to write player JSON files to')
@click.option('--write-all', '-a', is_flag=True, default=False,
              help='When multiple players match, write all without prompting')
def cli(player: str, bootstrap_path: str, output_dir: str, write_all: bool):
    """Extract player info from BOOTSTRAP and write a JSON file into OUTPUT_DIR."""

    if not os.path.exists(bootstrap_path):
        click.echo(f"bootstrap file not found: {bootstrap_path}", err=True)
        raise SystemExit(2)

    try:
        boot = load_bootstrap(bootstrap_path)
    except Exception as e:
        click.echo(f"Failed to load bootstrap file: {e}", err=True)
        raise SystemExit(3)

    pos_map = build_position_map(boot)
    team_map = build_team_map(boot)

    matches = find_players(boot, player)
    if not matches:
        click.echo(f"Player not found for query: '{player}'", err=True)
        raise SystemExit(1)

    # ensure output dir exists
    os.makedirs(output_dir, exist_ok=True)

    # If multiple matches and user didn't pass --write-all, offer interactive disambiguation
    selected = list(range(len(matches)))
    if len(matches) > 1 and not write_all:
        click.echo(f"Multiple players matched the query '{player}':")
        for idx, el in enumerate(matches, start=1):
            full_name = ((el.get('first_name') or '') + ' ' + (el.get('second_name') or '')).strip()
            team_info = team_map.get(el.get('team'))
            team_name = team_info.get('name') if team_info else str(el.get('team'))
            pos = pos_map.get(el.get('element_type'), str(el.get('element_type')))
            click.echo(f"  [{idx}] {full_name or el.get('web_name')} — {pos} — {team_name} (id={el.get('id')})")

        click.echo("Choose which player(s) to write by entering numbers separated by commas,")
        click.echo("or enter 'a' to write all, or just press Enter to cancel.")
        resp = click.prompt('Selection', default='', show_default=False)
        resp = (resp or '').strip()
        if resp.lower() == 'a':
            selected = list(range(len(matches)))
        elif resp == '':
            click.echo('No selection made; aborting.', err=True)
            raise SystemExit(0)
        else:
            # parse comma-separated list of indices
            try:
                parts = [int(p.strip()) for p in resp.split(',') if p.strip()]
                # convert to zero-based indices and filter
                selected = [p - 1 for p in parts if 1 <= p <= len(matches)]
                if not selected:
                    click.echo('No valid selection parsed; aborting.', err=True)
                    raise SystemExit(0)
            except ValueError:
                click.echo('Invalid selection input; aborting.', err=True)
                raise SystemExit(1)

    written = []
    for i, el in enumerate(matches, start=1):
        if (i - 1) not in selected:
            continue
        full_name = ((el.get('first_name') or '') + ' ' + (el.get('second_name') or '')).strip()
        position = pos_map.get(el.get('element_type'), str(el.get('element_type')))
        now_cost_raw = el.get('now_cost')
        try:
            cost = float(now_cost_raw) / 10.0 if now_cost_raw is not None else None
        except Exception:
            cost = now_cost_raw

        total_points = el.get('total_points')

        scoring_stats = {
            'minutes': el.get('minutes'),
            'goals_scored': el.get('goals_scored'),
            'assists': el.get('assists'),
            'clean_sheets': el.get('clean_sheets'),
            'goals_conceded': el.get('goals_conceded'),
            'own_goals': el.get('own_goals'),
            'penalties_saved': el.get('penalties_saved'),
            'penalties_missed': el.get('penalties_missed'),
            'yellow_cards': el.get('yellow_cards'),
            'red_cards': el.get('red_cards'),
            'saves': el.get('saves'),
            'bonus': el.get('bonus'),
            'bps': el.get('bps'),
            'influence': el.get('influence'),
            'creativity': el.get('creativity'),
            'threat': el.get('threat'),
            'ict_index': el.get('ict_index'),
            'expected_goals': el.get('expected_goals'),
            'expected_assists': el.get('expected_assists'),
            'expected_goal_involvements': el.get('expected_goal_involvements'),
            'expected_goals_conceded': el.get('expected_goals_conceded'),
            'points_per_game': el.get('points_per_game'),
            'event_points': el.get('event_points'),
            'ep_this': el.get('ep_this'),
            'ep_next': el.get('ep_next'),
        }

        # include team metadata (id + human name) instead of numeric id only
        team_info = team_map.get(el.get('team'))
        if team_info:
            team_field = team_info
        else:
            team_field = {"id": el.get('team')}

        out = {
            'name': full_name or el.get('web_name'),
            'position': position,
            'cost_million': cost,
            'total_points': total_points,
            'web_name': el.get('web_name'),
            'status': el.get('status'),
            'team': team_field,
            'scoring_stats': scoring_stats,
            'now_cost_raw': now_cost_raw,
        }

        # if multiple matches, append the element id to the filename for uniqueness
        base = sanitize_filename(full_name or el.get('web_name') or player)
        filename = f"{base}.json" if len(matches) == 1 else f"{base}_{el.get('id')}.json"
        out_path = os.path.join(output_dir, filename)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        written.append(out_path)

    click.echo(f"Wrote {len(written)} player file(s):")
    for p in written:
        click.echo(f"  {p}")


if __name__ == '__main__':
    cli()
