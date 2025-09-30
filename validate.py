import argparse
import json
import sys
import unicodedata
import re
from pathlib import Path

try:
    import yaml
except Exception:
    print(
        "Missing dependency: PyYAML is required. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)


def normalize(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace(".", " ").replace("-", " ").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_players_index(bootstrap: dict) -> list[dict]:
    # element_types: id -> short name (GK/DEF/MID/FWD)
    et_map = {
        et["id"]: et.get("singular_name_short", "")
        for et in bootstrap.get("element_types", [])
    }
    # teams: id -> metadata
    team_map = {
        t["id"]: {
            "name": t.get("name", ""),
            "short_name": t.get("short_name", ""),
            "code": t.get("code", ""),
        }
        for t in bootstrap.get("teams", [])
    }
    players = []
    for el in bootstrap.get("elements", []):
        p = {
            "id": el.get("id"),
            "web_name": el.get("web_name"),
            "first_name": el.get("first_name") or "",
            "second_name": el.get("second_name") or "",
            "now_cost": el.get("now_cost"),  # integer (usually tenths)
            "position": et_map.get(el.get("element_type"), ""),
            "team_id": el.get("team"),
            "team_name": team_map.get(el.get("team"), {}).get("name", ""),
            "team_short": team_map.get(el.get("team"), {}).get("short_name", ""),
            "team_code": team_map.get(el.get("team"), {}).get("code", ""),
        }
        p["norm_web"] = normalize(p["web_name"])
        p["norm_full"] = normalize(f"{p['first_name']} {p['second_name']}".strip())
        p["norm_second"] = normalize(p["second_name"])
        players.append(p)
    return players


def match_candidate(candidate: str, players: list[dict]) -> list[dict]:
    # candidate: a name like "Harry Kane" or "H. Kane". Optional team hint handled by caller
    n = normalize(candidate)
    matches = []
    for p in players:
        if n == p["norm_web"] or n == p["norm_full"] or n == p["norm_second"]:
            matches.append(p)
            continue
        # match initial forms like "M. Salah" or "M Salah"
        parts = n.split()
        if len(parts) >= 2:
            first, last = parts[0], " ".join(parts[1:])
            # initial check: single letter initial
            if len(first) == 1:
                if first == normalize(p["first_name"][:1]) and last == p["norm_second"]:
                    matches.append(p)
                    continue
            # leading initial with dot removed handled by normalize already
            if (
                len(first) == 2
                and first.endswith(".")
                and first[0] == normalize(p["first_name"][:1])
            ):
                if last == p["norm_second"]:
                    matches.append(p)
                    continue
        # try last name only if unique
        if n == p["norm_second"]:
            matches.append(p)
    return matches


def match_candidate_with_team(candidate: str, team_hint: str | None, players: list[dict]) -> list[dict]:
    """
    Match a candidate name, and optionally use a team_hint to filter ambiguous matches.
    The team_hint is normalized and compared against player's team_name, team_short, and team_code.
    """
    matches = match_candidate(candidate, players)
    if team_hint and matches:
        th = normalize(team_hint)
        filtered = []
        for p in matches:
            # compare team fields
            if th == normalize(p.get("team_name", "")):
                filtered.append(p)
                continue
            if th == normalize(p.get("team_short", "")):
                filtered.append(p)
                continue
            if th == normalize(p.get("team_code", "")):
                filtered.append(p)
                continue
        # If filtered non-empty, use it
        if filtered:
            return filtered
    return matches


def read_team_input(path: Path) -> list[str]:
    # Expect a plain text file: one player name per line
    with path.open("r", encoding="utf8") as fh:
        # Keep raw lines for potential parsing of team hints
        lines = [ln.rstrip() for ln in fh if ln.strip()]
    return lines


def parse_input_line(line: str) -> tuple[str, str | None]:
    """Parse a line which can be:
    - "Player Name"
    - "Player Name; Team Name"
    Returns (player_name, team_hint_or_None)
    """
    if ";" in line:
        parts = [p.strip() for p in line.split(";", 1)]
        name = parts[0]
        team_hint = parts[1] if len(parts) > 1 and parts[1] else None
        return name, team_hint
    return line.strip(), None


def write_validated_yaml(output: Path, validated: list[tuple]):
    # validated: list of (name, position, price, player_id, team_id, team_name)
    # Use PyYAML to produce a structured YAML document for easier consumption later.
    # Output structure:
    # team:
    #   Player Name:
    #     id: <player id>
    #     position: <GK/DEF/...>
    #     price: <float>
    #     team_id: <int>
    #     team_name: <string>
    out = {"team": {}}
    for entry in validated:
        # unpack with safety for older formats
        if len(entry) == 3:
            name, pos, price = entry
            pid = None
            team_id = None
            team_name = ""
        else:
            name, pos, price, pid, team_id, team_name = entry
        out_name = name
        out["team"][out_name] = {
            "id": pid,
            "position": pos,
            "price": float(price) if price is not None else None,
            "team_id": team_id,
            "team_name": team_name,
        }
    try:
        yaml.safe_dump(out, output.open("w", encoding="utf8"), sort_keys=False)
    except Exception:
        # fallback to manual writing if PyYAML fails for some reason
        with output.open("w", encoding="utf8") as fh:
            fh.write("team:\n")
            for name, pos, price, pid, team_id, team_name in validated:
                safe_name = name
                if ":" in name or name.startswith((" ", "-", "?")):
                    safe_name = f"'{name}'"
                fh.write(f"  {safe_name}:\n")
                fh.write(f"    id: {pid}\n")
                fh.write(f"    position: {pos}\n")
                fh.write(f"    price: {price:.1f}\n")
                fh.write(f"    team_id: {team_id}\n")
                fh.write(f"    team_name: '{team_name}'\n")


def main():
    ap = argparse.ArgumentParser(
        description="Validate a fantasy team against bootstrap-static.json"
    )
    ap.add_argument("-b", "--bootstrap", required=True, help="bootstrap-static.json")
    ap.add_argument(
        "-i", "--input", required=True, help="team file (plain .txt, one name per line)"
    )
    ap.add_argument(
        "-o", "--output", required=True, help="validated output (YAML can be in .txt)"
    )
    ap.add_argument(
        "--budget",
        type=float,
        default=100.0,
        help="Budget in millions (default: 100.0)",
    )
    ap.add_argument(
        "--no-enforce-rules",
        dest="enforce_rules",
        action="store_false",
        help="Disable enforcement of squad rules (still performs name matching)",
    )
    args = ap.parse_args()

    bpath = Path(args.bootstrap)
    ipath = Path(args.input)
    opath = Path(args.output)

    if not bpath.exists():
        print(f"Bootstrap file not found: {bpath}", file=sys.stderr)
        sys.exit(2)
    if not ipath.exists():
        print(f"Input team file not found: {ipath}", file=sys.stderr)
        sys.exit(2)

    bootstrap = json.loads(bpath.read_text(encoding="utf8"))
    players = build_players_index(bootstrap)
    team_list = read_team_input(ipath)
    if not team_list:
        print("No players found in input file.", file=sys.stderr)
        sys.exit(2)

    validated = []
    missing = []
    ambiguous = []
    for raw_line in team_list:
        candidate, team_hint = parse_input_line(raw_line)
        matches = match_candidate_with_team(candidate, team_hint, players)
        if len(matches) == 0:
            missing.append(candidate)
        elif len(matches) > 1:
            ambiguous.append(
                (
                    candidate,
                    [
                        f"{m['first_name']} {m['second_name']} ({m['web_name']})"
                        for m in matches
                    ],
                )
            )
        else:
            p = matches[0]
            price = (
                (p["now_cost"] / 10.0)
                if isinstance(p["now_cost"], (int, float))
                else None
            )
            validated.append(
                (
                    candidate,
                    p["position"] or "UNKNOWN",
                    price if price is not None else 0.0,
                    p.get("id"),
                    p.get("team_id"),
                    p.get("team_name") or "",
                )
            )

    if missing or ambiguous:
        if missing:
            print("Missing players (not found in bootstrap):", file=sys.stderr)
            for m in missing:
                print("  " + m, file=sys.stderr)
        if ambiguous:
            print("Ambiguous matches:", file=sys.stderr)
            for cand, opts in ambiguous:
                print(f"  {cand} -> {opts}", file=sys.stderr)
        sys.exit(3)

    # If enforcement is requested, run FPL rule checks
    def validate_rules(validated_list, budget_millions: float):
        # validated_list: entries with (name, position, price, pid, team_id, team_name)
        report = {"violations": [], "summary": {}}
        total_players = len(validated_list)
        total_cost = sum((p[2] or 0.0) for p in validated_list)
        # count positions
        counts = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0, "UNKNOWN": 0}
        club_counts = {}
        for entry in validated_list:
            _, pos, price, pid, team_id, team_name = entry
            counts[pos] = counts.get(pos, 0) + 1
            if team_id is not None:
                club_counts[team_id] = club_counts.get(team_id, 0) + 1

        report["summary"] = {
            "total_players": total_players,
            "total_cost": total_cost,
            "counts": counts,
            "club_counts": club_counts,
        }

        # FPL squad rules (standard):
        # - Squad size: exactly 15 players
        # - Position split: 2 GK, 5 DEF, 5 MID, 3 FWD (exact counts)
        # - Max 3 players from the same club
        # - Budget: total cost must be <= budget_millions (default 100.0)
        if total_players != 15:
            report["violations"].append(f"Squad size must be 15 (found {total_players})")
        # check exact position counts
        expected = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
        for k, v in expected.items():
            if counts.get(k, 0) != v:
                report["violations"].append(
                    f"Position {k} must be {v} (found {counts.get(k,0)})"
                )
        # clubs
        for team_id, cnt in club_counts.items():
            if cnt > 3:
                report["violations"].append(
                    f"More than 3 players from the same club (team_id={team_id}: {cnt})"
                )
        # budget
        if total_cost > budget_millions:
            report["violations"].append(
                f"Total squad cost {total_cost:.1f} > budget {budget_millions:.1f}"
            )

        return report

    # Run rules if requested
    report = None
    if args.enforce_rules:
        report = validate_rules(validated, args.budget)

    write_validated_yaml(opath, validated)
    print(f"Wrote validated team to {opath}")

    # Print short validation report
    if report is not None:
        print("Validation report:")
        print(f"  players: {report['summary']['total_players']}")
        print(f"  total_cost: {report['summary']['total_cost']:.1f}")
        print("  counts:")
        for k, v in report["summary"]["counts"].items():
            print(f"    {k}: {v}")
        if report["violations"]:
            print("  violations:")
            for v in report["violations"]:
                print(f"    - {v}")
            # non-zero exit on rule violation
            sys.exit(4)
        else:
            print("  status: OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
