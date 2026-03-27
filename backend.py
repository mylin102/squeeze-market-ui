from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = REPO_ROOT.parent
GENERATED_DIR = REPO_ROOT / "generated"


@dataclass(frozen=True)
class MarketConfig:
    code: str
    label: str
    repo_dir: Path
    analyze_placeholder: str


MARKETS: dict[str, MarketConfig] = {
    "US": MarketConfig(
        code="US",
        label="US Market",
        repo_dir=WORKSPACE_ROOT / "squeeze-us-screener",
        analyze_placeholder="UUUU",
    ),
    "TW": MarketConfig(
        code="TW",
        label="Taiwan Market",
        repo_dir=WORKSPACE_ROOT / "squeeze-tw-screener",
        analyze_placeholder="2330",
    ),
}


class CommandError(RuntimeError):
    pass


def _resolve_python(market: MarketConfig) -> str:
    specific_key = f"SQUEEZE_{market.code}_PYTHON"
    return os.environ.get(specific_key) or os.environ.get("SQUEEZE_PYTHON") or "python3"


def _run_cli(market: MarketConfig, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(market.repo_dir / "src")
    cmd = [_resolve_python(market), "-m", "squeeze.cli", *args]
    return subprocess.run(
        cmd,
        cwd=market.repo_dir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_analyze(market_code: str, ticker: str, pattern: str, period: str, fundamentals: bool) -> str:
    market = MARKETS[market_code]
    args = ["analyze", "--ticker", ticker, "--pattern", pattern, "--period", period]
    args.append("--fundamentals" if fundamentals else "--no-fundamentals")
    result = _run_cli(market, args)
    if result.returncode != 0:
        raise CommandError(result.stderr.strip() or result.stdout.strip() or "Analyze failed")
    return result.stdout.strip()


def run_plot(market_code: str, ticker: str, period: str) -> Path:
    market = MARKETS[market_code]
    market_dir = GENERATED_DIR / market.code.lower()
    market_dir.mkdir(parents=True, exist_ok=True)
    safe_ticker = ticker.strip().upper().replace(".", "_")
    output_path = market_dir / f"{safe_ticker}.png"
    result = _run_cli(market, ["plot", "--ticker", ticker, "--period", period, "--output", str(output_path)])
    if result.returncode != 0:
        raise CommandError(result.stderr.strip() or result.stdout.strip() or "Plot failed")
    if not output_path.exists():
        raise CommandError("Plot command completed but no PNG was created")
    return output_path
