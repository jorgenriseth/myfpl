rule bootstrap:
  output:
    "bootstrap-static.json"
  shell:
    "curl https://fantasy.premierleague.com/api/bootstrap-static/ | jq . > {output}"


#### Standard rule  #####
rule validate_team:
  input:
    "bootstrap-static.json",
    team="team{x}.txt"
  output:
    "team{x}_validated.yaml"
  shell:
    "python validate.py"
    " -i {input.team}"
    " -o {output}"
    " -b {input[0]}"


#### Directory Outputer / Unknown files outputs ####
rule score_players:
  input:
    "team{x}_validated.txt"
  output:
    directory("team{x}_playerscores/")
  script:
    "team_player_scores.py"


#### Use standard Python, here to define input functions ####
# from pathlib import Path
# import pandas as pd

# def list_players(dir: str | Path) -> list[str]:
#   player_files = Path(dir).glob("*.json")
#   return [player.stem for player in player_files]


# rule team_player_scores_table:
#   input:
#     lambda wc: f"team{wc.x}_playerscores/"#{player}.csv" for player in list_players(f"team{wc.x}_playerscores/")]
#   output:
#     "team{x}_score.csv"
#   run:
#     records = []
#     for p in input:
#       with open(p, "r") as f:
#         records.append(json.load(f))
#     pd.DataFrame.from_records(records).to_csv(Path(output))


# rule team_score_report:
#   input: "team{x}_score.csv"
#   output: "logs/team{x}_report.ipynb"
#   log: "logs/team{x}_performance.ipynb"
#   notebook: "notebooks/team{x}_performance.ipynb"
