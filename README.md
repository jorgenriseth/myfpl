validate.py
===========

Usage
-----

The `validate.py` script validates a plain-text team list against an FPL `bootstrap-static.json` dump.

Input format
------------
- One player per line.
- To disambiguate players with identical or ambiguous names you may add a team hint after a semicolon.

Examples:

- `Harry Kane`  (simple name)
- `White; Arsenal`  (name `White`, hint `Arsenal` to disambiguate between multiple Whites)

The script outputs a YAML file with per-player `id`, `position`, `price`, `team_id` and `team_name`.

Validation rules
----------------
By default the script enforces the standard FPL squad rules:

- Squad size: 15 players
- Positions: 2 GK, 5 DEF, 5 MID, 3 FWD
- Max 3 players from the same club
- Budget: default 100.0 (millions) — configurable with `--budget`

You can disable enforcement with `--no-enforce-rules`.
