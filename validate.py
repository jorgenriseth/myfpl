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
    players = []
    for el in bootstrap.get("elements", []):
        p = {
            "id": el.get("id"),
            "web_name": el.get("web_name"),
            "first_name": el.get("first_name") or "",
            "second_name": el.get("second_name") or "",
            "now_cost": el.get("now_cost"),  # integer (usually tenths)
            "position": et_map.get(el.get("element_type"), ""),
        }
        p["norm_web"] = normalize(p["web_name"])
        p["norm_full"] = normalize(f"{p['first_name']} {p['second_name']}".strip())
        p["norm_second"] = normalize(p["second_name"])
        players.append(p)
    return players


def match_candidate(candidate: str, players: list[dict]) -> list[dict]:
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


def read_team_input(path: Path) -> list[str]:
    # Expect a plain text file: one player name per line
    with path.open("r", encoding="utf8") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]
    return lines


def write_validated_yaml(output: Path, validated: list[tuple]):
    # validated: list of (name, position, price)
    with output.open("w", encoding="utf8") as fh:
        fh.write("team:\n")
        for name, pos, price in validated:
            # quote the name if it contains colon or special chars
            safe_name = name
            if ":" in name or name.startswith((" ", "-", "?")):
                safe_name = f"'{name}'"
            fh.write(f"  {safe_name}:\n")
            fh.write(f"    position: {pos}\n")
            fh.write(f"    price: {price:.1f}\n")


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
    for candidate in team_list:
        matches = match_candidate(candidate, players)
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

    write_validated_yaml(opath, validated)
    print(f"Wrote validated team to {opath}")
    sys.exit(0)


if __name__ == "__main__":
    main()
