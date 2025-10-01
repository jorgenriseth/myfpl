# configfile: "config.yaml"

# rule all:
#   input:
#     [
#       f"figures/team{x}_performance.png"
#       for x in config["teams"]
#     ] 


rule download_base_data:
  output:
    "base-data.json",
  shell:
    "curl https://fantasy.premierleague.com/api/bootstrap-static/ | jq . > {output[0]}; " 

rule download_fixture_data:
  output:
    fixtures="fixtures.json"
  shell:
    "python src/myfpl/fixtures.py --output {output.fixtures}"


from pathlib import Path
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


rule player_score_plot:
  input:
    "players/{player}.json"
  output:
    "figures/{player}.png"
  script:
    "scripts/player_score_plot.py"



rule validate_team:
  input:
    bootstrap="base-data.json",
    team="team{x}.txt"
  output:
    "team{x}_validated.yaml"
  shell:
    "python src/myfpl/validate.py -i {input.team} -o {output} -b {input.bootstrap}"


### Normal Python function to read yaml file ###

import yaml

def list_norm_full_names(yaml_path):
  with open(yaml_path, "r", encoding="utf8") as f:
    data = yaml.safe_load(f)
  players =  [player_info["norm_full_name"] for player_info in data["team"].values()]
  return players


ruleorder: team_report > player_score_plot
rule team_report:
  input:
    validated="team{x}_validated.yaml",
    players=lambda wildcards: list(f"players/{player}.json" for player in list_norm_full_names(f"team{wildcards.x}_validated.yaml"))
  output:
    "figures/team{x}_performance.png"
  log:
    notebook="logs/team{x}_performance.ipynb"
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

