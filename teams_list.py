#!/usr/bin/env python3
"""List teams and their IDs from a Fantasy FPL `bootstrap-static.json`.

Usage examples:
  pixi run python3 teams_list.py --bootstrap bootstrap-static.json --format json --output teams.json
  pixi run python3 teams_list.py --format csv > teams.csv
"""
import json
import os
from typing import List, Dict
import click


def load_bootstrap(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_teams(bootstrap: dict) -> List[Dict]:
    teams = []
    for t in bootstrap.get("teams", []):
        teams.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "short_name": t.get("short_name"),
            "code": t.get("code"),
        })
    return teams


@click.command()
@click.option("--bootstrap", "bootstrap_path", default="bootstrap-static.json", show_default=True,
              help="Path to bootstrap-static.json")
@click.option("--format", "out_format", default="json", type=click.Choice(["json", "csv", "pretty"]),
              show_default=True, help="Output format")
@click.option("--output", "output_path", default=None, help="File to write output to (if omitted prints to stdout)")
def cli(bootstrap_path: str, out_format: str, output_path: str):
    if not os.path.exists(bootstrap_path):
        click.echo(f"bootstrap file not found: {bootstrap_path}", err=True)
        raise SystemExit(2)

    boot = load_bootstrap(bootstrap_path)
    teams = extract_teams(boot)

    if out_format == "json":
        text = json.dumps(teams, ensure_ascii=False, indent=2)
    elif out_format == "pretty":
        lines = [f"{t['id']:>3}  {t['short_name'] or '' :<6}  {t['name']}" for t in teams]
        text = "\n".join(lines)
    else:  # csv
        rows = ["id,short_name,name"]
        for t in teams:
            # escape commas in name
            name = (t['name'] or '').replace('"', '""')
            short = (t['short_name'] or '').replace('"', '""')
            rows.append(f'{t["id"]},"{short}","{name}"')
        text = "\n".join(rows)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        click.echo(f"Wrote teams to: {output_path}")
    else:
        click.echo(text)


if __name__ == "__main__":
    cli()
