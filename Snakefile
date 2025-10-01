from pathlib import Path

rule minimal_rule:
  shell:
    "echo 'This is a minimal rule'"


rule download_base_data:
  output:
    "base-data.json",
    fixtures="fixtures.json"
  shell:
    "curl https://fantasy.premierleague.com/api/bootstrap-static/ | jq . > {output[0]}; " 
    "python src/myfpl/fixtures.py --output {output.fixtures}"


#####################
# PARAMS & python-functions
#####################
def output_dir(wildcards, output):
  return Path(output[0]).parent


rule parse_player:
  input:
    bootstrap="base-data.json",
    fixtures="fixtures.json"
  output:
    "players/{player}.json"
  params:
    outdir=output_dir
  shell:
    "python src/myfpl/player.py"
    " --player {wildcards.player}"
    " --bootstrap {input.bootstrap}"
    " --output-dir {params.outdir}"
    " --fixtures {input.fixtures};"
    " echo {wildcards.player} completed!; sleep 5"


# rule player_score_plot:
#   input:
#     "players/{player}.json"
#   output:
#     "figures/{player}.png"
#   script:
#     "scripts/player_score_plot.py"



#### Standard rule  #####
rule validate_team:
  input:
    bootstrap="base-data.json",
    team="team{x}.txt"
  output:
    "team{x}_validated.yaml"
  shell:
    "python src/myfpl/validate.py -i {input.team} -o {output} -b {input.bootstrap}"


import yaml

def list_norm_full_names(yaml_path):
  with open(yaml_path, "r", encoding="utf8") as f:
    data = yaml.safe_load(f)
  return [player_info["norm_full_name"] for player_info in data["team"].values()]


ruleorder: team_report > score_players
rule team_report:
  input:
    validated="team{x}_validated.yaml",
    players=lambda wildcards: list(f"players/{player}.json" for player in list_norm_full_names(f"team{wildcards.x}_validated.yaml"))
  output:
    "figures/team{x}_performance.png"
  log:
    notebook="logs/team{x}_performance.ipynb"
  # run:
  #   with open(str(output), "w") as out_f:
  #     for player in input.players:
  #       print(player)
  #       out_f.write(f"Player data from {player}\n")
  notebook:
    "notebooks/team_performance.ipynb"


#### Directory Outputter / Unknown files outputs ####
rule score_players:
  input:
    "team{x}_validated.yaml"
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
