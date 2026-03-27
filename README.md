# Squeeze Market UI

Streamlit MVP for running single-ticker `analyze` and `plot` workflows against the local `squeeze-us-screener` and `squeeze-tw-screener` repos.

## Features
- Switch between `US` and `TW`
- Run single-ticker analysis from a web UI
- Generate and preview chart PNGs
- Reuse the existing CLI commands from sibling repos instead of duplicating logic

## Repo Layout
- `app.py`: Streamlit entrypoint
- `backend.py`: subprocess wrapper around the US/TW CLIs
- `generated/`: chart output directory at runtime

## Requirements
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
cd /Users/mingyenlin/Documents/GWork/mylin102/squeeze-market-ui
streamlit run app.py
```

## Assumptions
- The sibling repos exist:
  - `/Users/mingyenlin/Documents/GWork/mylin102/squeeze-us-screener`
  - `/Users/mingyenlin/Documents/GWork/mylin102/squeeze-tw-screener`
- The selected repo can already run locally via:
  - `PYTHONPATH=src python3 -m squeeze.cli analyze --ticker ...`
  - `PYTHONPATH=src python3 -m squeeze.cli plot --ticker ...`
- By default the UI calls sibling CLIs with `python3`. If needed, override with:
  - `SQUEEZE_PYTHON`
  - `SQUEEZE_US_PYTHON`
  - `SQUEEZE_TW_PYTHON`
