from pathlib import Path

rule minimal_rule:
  shell:
    "echo 'This is a minimal rule' > minimal.txt"


rule download_base_data:
  output:
    "base-data.json"
  shell:
    "curl https://fantasy.premierleague.com/api/bootstrap-static/ | jq . > {output}"


rule fixtures_map:
  output:
    "players/fixtures.json"
  shell:
    "python -m myfpl.fixtures --output {output}"


def output_dir(_, output):
  return Path(output[0]).parent


rule parse_player:
  input:
    bootstrap="base-data.json",
    fixtures="players/fixtures.json"
  output:
    "players/{player}.json"
  params:
    outdir=output_dir
  shell:
    "python -m myfpl.player --player {wildcards.player} --bootstrap {input.bootstrap} --output-dir {params.outdir} --fixtures {input.fixtures}"


rule player_score_plot:
  input:
    "players/{player}.json"
  output:
    "players/{player}.png"
  script:
    "scripts/player_score_plot.py"



#### Standard rule  #####
rule validate_team:
  input:
    bootstrap="base-data.json",
    team="team{x}.txt"
  output:
    "team{x}_validated.yaml"
  shell:
    "python validate.py -i {input.team} -o {output} -b {input.bootstrap}"


#### Directory Outputer / Unknown files outputs ####
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
