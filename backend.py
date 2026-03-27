from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import io
import os

# Configure env before importing pandas_ta/matplotlib-related modules.
REPO_ROOT = Path(__file__).resolve().parent
GENERATED_DIR = REPO_ROOT / "generated"
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
os.environ.setdefault("MPLCONFIGDIR", str((REPO_ROOT / ".mplconfig").resolve()))

import mplfinance as mpf
import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
import urllib3
import yfinance as yf


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass(frozen=True)
class MarketConfig:
    code: str
    label: str
    analyze_placeholder: str


MARKETS: dict[str, MarketConfig] = {
    "US": MarketConfig("US", "US Market", "UUUU"),
    "TW": MarketConfig("TW", "Taiwan Market", "2330"),
}

PATTERN_LABELS = {
    "squeeze": "Squeeze",
    "houyi": "Houyi",
    "whale": "Whale",
}

PATTERN_EXPLANATIONS = {
    "squeeze": "Focuses on volatility compression, whether the squeeze is on, and whether momentum is strengthening or firing.",
    "houyi": "Looks for a strong prior rally, pullback into a Fibonacci zone, and a shooting-star style candle while squeeze conditions persist.",
    "whale": "Checks whether daily and weekly timeframes are aligned, both with squeeze structure and positive momentum.",
}


class CommandError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _fetch_tw_ticker_map() -> dict[str, str]:
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEx": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
        "Emerging": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=5",
    }
    ticker_map: dict[str, str] = {}
    for market, url in urls.items():
        response = requests.get(url, verify=False, timeout=20)
        response.encoding = "big5"
        tables = pd.read_html(io.StringIO(response.text))
        data = tables[0].iloc[1:, 0]
        for entry in data:
            if not isinstance(entry, str):
                continue
            parts = entry.split("\u3000")
            if len(parts) < 2:
                continue
            code = parts[0].strip()
            name = parts[1].strip()
            if len(code) == 4 and code.isdigit():
                suffix = ".TW" if market == "TWSE" else ".TWO"
                ticker_map[f"{code}{suffix}"] = name
    return ticker_map


def _normalize_ticker(market_code: str, raw_ticker: str) -> tuple[str, str]:
    ticker = raw_ticker.strip().upper()
    if market_code == "US":
        return ticker, ticker

    ticker_map = _fetch_tw_ticker_map()
    if ticker in ticker_map:
        return ticker, ticker_map[ticker]
    if "." not in ticker and ticker.isdigit():
        for suffix in (".TW", ".TWO"):
            candidate = f"{ticker}{suffix}"
            if candidate in ticker_map:
                return candidate, ticker_map[candidate]
    return ticker, ticker


def _download_single_ticker(ticker: str, period: str) -> pd.DataFrame:
    df = yf.download(ticker, period=period, auto_adjust=False, progress=False, threads=False)
    if df.empty:
        raise CommandError(f"No market data available for {ticker}.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.capitalize() for c in df.columns]
    required = ["Open", "High", "Low", "Close", "Volume"]
    for col in required:
        if col not in df.columns:
            raise CommandError(f"Missing required column: {col}")
    return df.dropna(subset=["Close"]).copy()


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    sqz = df.ta.squeeze(bb_length=20, bb_std=2.0, kc_length=20, kc_scalar=1.5, lazy=True)
    sqz_on_col = [c for c in sqz.columns if "SQZ_ON" in c][0]
    mom_col = [c for c in sqz.columns if c.startswith("SQZ_") and c not in ["SQZ_ON", "SQZ_OFF", "SQZ_NO"]][0]

    bb = df.ta.bbands(length=20, std=2.0)
    kc = df.ta.kc(length=20, scalar=1.5)
    bb_upper = bb.filter(like="BBU").iloc[:, 0]
    bb_lower = bb.filter(like="BBL").iloc[:, 0]
    kc_upper = kc.filter(like="KCU").iloc[:, 0]
    kc_lower = kc.filter(like="KCL").iloc[:, 0]
    bb_width = bb_upper - bb_lower
    kc_width = kc_upper - kc_lower
    squeeze_ratio = ((kc_width - bb_width) / kc_width).clip(lower=0, upper=1)
    energy_level = pd.cut(
        squeeze_ratio,
        bins=[-np.inf, 0.3, 0.5, 0.7, np.inf],
        labels=[0, 1, 2, 3],
    ).fillna(0).astype(int)

    result = df.copy()
    result["Squeeze_On"] = sqz[sqz_on_col].astype(bool)
    result["Energy_Level"] = energy_level
    result["Momentum"] = sqz[mom_col].fillna(0)
    result["Prev_Momentum"] = result["Momentum"].shift(1).fillna(0)
    result["Fired"] = (~result["Squeeze_On"]) & (result["Squeeze_On"].shift(1) == True)
    result["Fired"] = result["Fired"].fillna(False)

    def determine_signal(row: pd.Series) -> str:
        mom = row["Momentum"]
        prev_mom = row["Prev_Momentum"]
        fired = row["Fired"]
        if fired and mom > 0:
            return "強烈買入 (爆發)"
        if fired and mom < 0:
            return "強烈賣出 (跌破)"
        if mom > 0:
            return "買入 (動能增強)" if mom > prev_mom else "觀望 (動能減弱)"
        return "觀察 (跌勢收斂)" if mom > prev_mom else "賣出 (動能轉弱)"

    result["Signal"] = result.apply(determine_signal, axis=1)
    return result


def _detect_squeeze(df: pd.DataFrame) -> dict:
    latest = _calculate_indicators(df).iloc[-1]
    return {
        "Signal": str(latest["Signal"]),
        "Close": float(latest["Close"]),
        "squeeze_on": bool(latest["Squeeze_On"]),
        "fired": bool(latest["Fired"]),
        "energy_level": int(latest["Energy_Level"]),
        "momentum": float(latest["Momentum"]),
        "prev_momentum": float(latest["Prev_Momentum"]),
        "timestamp": str(latest.name),
        "Squeeze Match": "Yes" if bool(latest["Squeeze_On"]) or bool(latest["Fired"]) else "No",
    }


def _detect_houyi(df: pd.DataFrame) -> dict:
    dfi = _calculate_indicators(df)
    latest = dfi.iloc[-1]
    window = df.iloc[-60:]
    peak_idx = window["High"].idxmax()
    peak_price = window["High"].max()
    peak_pos = df.index.get_loc(peak_idx)
    start_pos = max(0, peak_pos - 30)
    trough_price = df.iloc[start_pos:peak_pos + 1]["Low"].min()
    rally_pct = (peak_price - trough_price) / trough_price if trough_price > 0 else 0.0
    fib_level = (peak_price - latest["Close"]) / (peak_price - trough_price) if peak_price > trough_price else 0.0
    shooting_star = False
    for _, bar in df.iloc[-5:].iterrows():
        body = abs(bar["Close"] - bar["Open"])
        upper_wick = bar["High"] - max(bar["Close"], bar["Open"])
        if (body < 0.001 and upper_wick > 0) or (body >= 0.001 and (upper_wick / body) >= 2.0):
            shooting_star = True
            break
    is_houyi = rally_pct >= 0.2 and 0.4 <= fib_level <= 0.75 and bool(latest["Squeeze_On"]) and shooting_star
    return {
        "Signal": str(latest["Signal"]),
        "Close": float(latest["Close"]),
        "squeeze_on": bool(latest["Squeeze_On"]),
        "fired": bool(latest["Fired"]),
        "energy_level": int(latest["Energy_Level"]),
        "momentum": float(latest["Momentum"]),
        "prev_momentum": float(latest["Prev_Momentum"]),
        "Houyi Match": "Yes" if is_houyi else "No",
        "Rally %": f"{rally_pct:.2%}",
        "Fib Level": f"{fib_level:.3f}",
        "Shooting Star": "Yes" if shooting_star else "No",
    }


def _detect_whale(df: pd.DataFrame) -> dict:
    dfi = _calculate_indicators(df)
    latest_daily = dfi.iloc[-1]
    weekly = df.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    if len(weekly) >= 30:
        latest_weekly = _calculate_indicators(weekly).iloc[-1]
        weekly_sq = bool(latest_weekly["Squeeze_On"])
        weekly_mom = float(latest_weekly["Momentum"])
    else:
        weekly_sq = False
        weekly_mom = 0.0
    daily_sq = bool(latest_daily["Squeeze_On"])
    daily_mom = float(latest_daily["Momentum"])
    is_whale = daily_sq and weekly_sq and daily_mom > 0 and weekly_mom > 0
    return {
        "Signal": str(latest_daily["Signal"]),
        "Close": float(latest_daily["Close"]),
        "squeeze_on": daily_sq,
        "fired": bool(latest_daily["Fired"]),
        "energy_level": int(latest_daily["Energy_Level"]),
        "momentum": daily_mom,
        "prev_momentum": float(latest_daily["Prev_Momentum"]),
        "Whale Match": "Yes" if is_whale else "No",
        "Daily Squeeze": "Yes" if daily_sq else "No",
        "Weekly Squeeze": "Yes" if weekly_sq else "No",
        "Daily Momentum": f"{daily_mom:.4f}",
        "Weekly Momentum": f"{weekly_mom:.4f}",
    }


def _build_houyi_overlays(df: pd.DataFrame) -> tuple[list, str]:
    window = df.iloc[-60:]
    peak_idx = window["High"].idxmax()
    peak_price = window["High"].max()
    peak_pos = df.index.get_loc(peak_idx)
    start_pos = max(0, peak_pos - 30)
    trough_price = df.iloc[start_pos:peak_pos + 1]["Low"].min()
    fib_50 = peak_price - (peak_price - trough_price) * 0.5
    fib_618 = peak_price - (peak_price - trough_price) * 0.618

    overlays = [
        mpf.make_addplot(pd.Series(fib_50, index=df.index), color="purple", width=1, alpha=0.6),
        mpf.make_addplot(pd.Series(fib_618, index=df.index), color="magenta", width=1, alpha=0.6),
    ]

    marker = pd.Series(np.nan, index=df.index)
    for idx, bar in df.iloc[-5:].iterrows():
        body = abs(bar["Close"] - bar["Open"])
        upper_wick = bar["High"] - max(bar["Close"], bar["Open"])
        if (body < 0.001 and upper_wick > 0) or (body >= 0.001 and (upper_wick / body) >= 2.0):
            marker.loc[idx] = bar["High"] * 1.02
    if marker.notna().any():
        overlays.append(mpf.make_addplot(marker, type="scatter", marker="v", markersize=80, color="purple"))

    subtitle = f"Houyi Fib Zone: 0.500={fib_50:.2f}, 0.618={fib_618:.2f}"
    return overlays, subtitle


def _build_whale_panel(df: pd.DataFrame) -> tuple[list, str]:
    weekly = df.resample("W").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    if len(weekly) < 30:
        return [], "Whale: insufficient weekly history"

    weekly_ind = _calculate_indicators(weekly)
    weekly_momentum = weekly_ind["Momentum"].reindex(df.index, method="ffill")
    weekly_squeeze = bool(weekly_ind.iloc[-1]["Squeeze_On"])
    overlays = [
        mpf.make_addplot(weekly_momentum.tail(252), panel=3, color="gold", secondary_y=False, ylabel="Weekly Mom")
    ]
    subtitle = f"Whale Alignment: weekly squeeze={'Yes' if weekly_squeeze else 'No'}, weekly momentum={weekly_ind.iloc[-1]['Momentum']:.4f}"
    return overlays, subtitle


def _plot_ticker(df: pd.DataFrame, ticker_symbol: str, output_path: Path, pattern: str) -> None:
    data = _calculate_indicators(df)
    bb = data.ta.bbands(length=20, std=2.0)
    kc = data.ta.kc(length=20, scalar=1.5)
    data["BB_Upper"] = bb.filter(like="BBU").iloc[:, 0]
    data["BB_Lower"] = bb.filter(like="BBL").iloc[:, 0]
    data["KC_Upper"] = kc.filter(like="KCU").iloc[:, 0]
    data["KC_Lower"] = kc.filter(like="KCL").iloc[:, 0]
    plot_df = data.tail(252).copy()

    hist_colors = []
    for i in range(len(plot_df["Momentum"])):
        val = plot_df["Momentum"].iloc[i]
        prev_val = plot_df["Momentum"].iloc[i - 1] if i > 0 else 0
        if val >= 0:
            hist_colors.append("cyan" if val >= prev_val else "blue")
        else:
            hist_colors.append("red" if val <= prev_val else "maroon")

    plots = [
        mpf.make_addplot(plot_df["BB_Upper"], color="blue", linestyle="dashed", alpha=0.2),
        mpf.make_addplot(plot_df["BB_Lower"], color="blue", linestyle="dashed", alpha=0.2),
        mpf.make_addplot(plot_df["KC_Upper"], color="orange", alpha=0.2),
        mpf.make_addplot(plot_df["KC_Lower"], color="orange", alpha=0.2),
        mpf.make_addplot(plot_df["Momentum"], type="bar", panel=1, color=hist_colors, secondary_y=False, ylabel="Momentum"),
        mpf.make_addplot(np.full(len(plot_df), 1.0), type="bar", panel=2, color=np.where(plot_df["Squeeze_On"], "black", "#cccccc"), width=1.0, secondary_y=False, ylabel="SQZ"),
    ]

    panel_ratios = (6, 2, 1)
    subtitle = "Squeeze Structure: BB/KC compression, momentum histogram, squeeze ribbon"
    if pattern == "houyi":
        houyi_plots, subtitle = _build_houyi_overlays(plot_df)
        plots.extend(houyi_plots)
    elif pattern == "whale":
        whale_plots, subtitle = _build_whale_panel(data)
        plots.extend(whale_plots)
        if whale_plots:
            panel_ratios = (6, 2, 1, 2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mpf.plot(
        plot_df,
        type="candle",
        style="charles",
        addplot=plots,
        title=f"\n{ticker_symbol} - {PATTERN_LABELS[pattern]} Analysis (1yr)\n{subtitle}",
        savefig=str(output_path),
        volume=True,
        panel_ratios=panel_ratios,
        datetime_format="%Y-%m",
        xrotation=0,
        show_nontrading=False,
        tight_layout=True,
    )


def run_analyze(market_code: str, ticker: str, pattern: str, period: str) -> str:
    normalized_ticker, display_name = _normalize_ticker(market_code, ticker)
    df = _download_single_ticker(normalized_ticker, period)
    detectors = {
        "squeeze": _detect_squeeze,
        "houyi": _detect_houyi,
        "whale": _detect_whale,
    }
    if pattern not in detectors:
        raise CommandError(f"Unknown pattern: {pattern}")
    result = detectors[pattern](df)
    rows = [
        ("Pattern", PATTERN_LABELS[pattern]),
        ("Pattern Focus", PATTERN_EXPLANATIONS[pattern]),
        ("Ticker", normalized_ticker),
        ("Name", display_name),
        ("Period", period),
    ]

    common_keys = ["Signal", "Close", "squeeze_on", "fired", "energy_level", "momentum", "prev_momentum"]
    pattern_specific_keys = {
        "squeeze": ["Squeeze Match", "timestamp"],
        "houyi": ["Houyi Match", "Rally %", "Fib Level", "Shooting Star"],
        "whale": ["Whale Match", "Daily Squeeze", "Weekly Squeeze", "Daily Momentum", "Weekly Momentum"],
    }

    for key in common_keys:
        if key in result:
            rows.append((key, result[key]))
    for key in pattern_specific_keys[pattern]:
        if key in result:
            rows.append((key, result[key]))

    return "\n".join(f"{key}: {value}" for key, value in rows)


def run_plot(market_code: str, ticker: str, period: str, pattern: str) -> Path:
    normalized_ticker, _ = _normalize_ticker(market_code, ticker)
    df = _download_single_ticker(normalized_ticker, period)
    market_dir = GENERATED_DIR / market_code.lower()
    safe_ticker = normalized_ticker.replace(".", "_")
    output_path = market_dir / f"{safe_ticker}_{pattern}.png"
    _plot_ticker(df, normalized_ticker, output_path, pattern)
    return output_path
