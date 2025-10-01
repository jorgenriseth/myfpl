"""Snakemake script: plot player scores per gameweek.

Reads a player JSON from snakemake.input[0] and writes a PNG to snakemake.output[0].

This file is intended to be used from a Snakemake rule with `script:`.
"""

import json
from pathlib import Path
import sys
from typing import List, Tuple, Dict

import matplotlib

# Use a non-interactive backend which is safe in CI/envs without display
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_player(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_gameweek_scores(player: Dict) -> Tuple[List[int], List[int]]:
    """Return lists (gameweeks, scores).

    - Include only entries where 'event' is an int (not null).
    - Sort by event number.
    """
    history = player.get("history", [])
    rows = []
    for entry in history:
        event = entry.get("event")
        score = entry.get("total_score")
        # skip aggregated season totals where event is null
        if event is None:
            continue
        try:
            event_i = int(event)
        except Exception:
            continue
        try:
            score_i = int(score)
        except Exception:
            # if score missing or invalid, use 0
            score_i = 0
        rows.append((event_i, score_i))
    # sort by event
    rows.sort(key=lambda x: x[0])
    if not rows:
        return [], []
    gw, scores = zip(*rows)
    return list(gw), list(scores)


def plot_scores(
    gameweeks: List[int], scores: List[int], player_name: str, outpath: Path
) -> None:
    plt.figure(figsize=(max(6, len(gameweeks) * 0.6), 4))
    plt.bar(gameweeks, scores, color="#1f77b4")
    plt.xlabel("Gameweek")
    plt.ylabel("Total points")
    plt.title(f"{player_name} — gameweek points")
    plt.xticks(gameweeks)
    plt.tight_layout()
    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(outpath)
    plt.close()


def main():
    inp = Path(str(snakemake.input[0]))
    outp = Path(str(snakemake.output[0]))

    player = read_player(inp)
    gw, scores = extract_gameweek_scores(player)
    player_name = player.get("name") or player.get("web_name") or inp.stem
    if not gw:
        # create an empty figure with message
        plt.figure(figsize=(6, 3))
        plt.text(0.5, 0.5, "No gameweek history available", ha="center", va="center")
        plt.axis("off")
        outp.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(outp)
        plt.close()
        return

    plot_scores(gw, scores, player_name, outp)


if __name__ == "__main__":
    main()
