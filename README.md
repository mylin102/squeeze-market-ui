# Squeeze Market UI

Streamlit MVP for running single-ticker `analyze` and `plot` workflows for US and Taiwan markets from a single self-contained repo.

## Features
- Switch between `US` and `TW`
- Run single-ticker analysis from a web UI
- Generate and preview chart PNGs
- Self-contained backend for `analyze` and `plot`
- Ready to adapt for Streamlit Community Cloud deployment

## Repo Layout
- `app.py`: Streamlit entrypoint
- `backend.py`: self-contained market analysis, Taiwan ticker normalization, and chart generation
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

## Notes
- US ticker example: `UUUU`
- Taiwan ticker example: `2330`
- Taiwan input supports shorthand and will resolve to `.TW` or `.TWO`
- For Streamlit Community Cloud, this repo no longer depends on sibling repos
