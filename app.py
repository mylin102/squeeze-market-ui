from __future__ import annotations

from pathlib import Path

import streamlit as st

from backend import CommandError, MARKETS, run_analyze, run_plot


st.set_page_config(page_title="Squeeze Market UI", layout="wide")

st.title("Squeeze Market UI")
st.caption("Streamlit MVP for single-ticker analysis and chart generation.")

with st.sidebar:
    market_code = st.selectbox("Market", options=list(MARKETS.keys()), format_func=lambda code: MARKETS[code].label)
    pattern = st.selectbox("Pattern", ["squeeze", "houyi", "whale"])
    period = st.selectbox("Period", ["2y", "1y", "6mo"])
    fundamentals = st.toggle("Include Fundamentals", value=True)

market = MARKETS[market_code]

col1, col2 = st.columns([2, 1])
with col1:
    ticker = st.text_input("Ticker", placeholder=market.analyze_placeholder)
with col2:
    st.markdown("### Notes")
    if market_code == "TW":
        st.write("台股可直接輸入 `2330`，CLI 會自動補成 `.TW` 或 `.TWO`。")
    else:
        st.write("美股請直接輸入標準 ticker，例如 `UUUU`。")

action_col1, action_col2 = st.columns(2)
analyze_clicked = action_col1.button("Analyze", use_container_width=True)
plot_clicked = action_col2.button("Plot", use_container_width=True)

if not ticker.strip():
    st.info("輸入 ticker 後再執行 Analyze 或 Plot。")
else:
    if analyze_clicked:
        st.subheader("Analysis Output")
        with st.spinner(f"Running analyze for {ticker.strip()}..."):
            try:
                output = run_analyze(market_code, ticker.strip(), pattern, period, fundamentals)
                st.code(output or "(no output)", language="text")
            except CommandError as exc:
                st.error(str(exc))

    if plot_clicked:
        st.subheader("Chart Preview")
        with st.spinner(f"Generating chart for {ticker.strip()}..."):
            try:
                output_path = run_plot(market_code, ticker.strip(), period)
                st.image(str(output_path), caption=str(output_path.relative_to(Path(__file__).resolve().parent)))
            except CommandError as exc:
                st.error(str(exc))
