"""
Portfolio Analyst — Bloomberg Terminal Edition
===============================================
Quantitative analysis of an international equity portfolio with a
premium, dark-themed visual style inspired by professional terminals.

Metrics
-------
    Sharpe Ratio · Sortino Ratio · Beta (CAPM) · Maximum Drawdown

Optimisation
------------
    Log-returns · Covariance matrix · Inverse-Variance weights

Charts
------
    1. Cumulative Returns   (Bloomberg Terminal dark aesthetic)
    2. Historical Drawdown  (Bloomberg Terminal dark aesthetic)

Author  : Senior Quantitative Developer
Date    : 2026-03-16
Python  : 3.9+
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.axes import Axes
from matplotlib.figure import Figure
import numpy as np
import pandas as pd
import yfinance as yf

# ──────────────────────────────────────────────────────────────────────────────
# Domain constants  (no magic numbers anywhere in the codebase)
# ──────────────────────────────────────────────────────────────────────────────

TRADING_DAYS: int = 252          # calendar-year annualisation factor
RISK_FREE_RATE: float = 0.04     # annual risk-free rate  (~4 % 3-m T-Bill)
BENCHMARK_TICKER: str = "SPY"    # S&P 500 ETF — market proxy for Beta

# ── Bloomberg Terminal design tokens ─────────────────────────────────────────

BG_FIGURE: str = "#121212"       # outer figure background
BG_AXES: str   = "#1a1a1a"       # plot-area background (slightly lighter)
CLR_TITLE: str = "#e0e0e0"       # chart title colour
CLR_LABEL: str = "#9e9e9e"       # axis label & tick colour
CLR_GRID: str  = "#ffffff"       # grid line colour (very low alpha)
CLR_ZERO: str  = "#555555"       # zero-line colour
CLR_SPINE: str = "#333333"       # visible spine (bottom + left) colour
GRID_ALPHA: float = 0.15         # grid transparency  (subtle)
GRID_STYLE: str   = "--"         # grid dash style
LINE_WIDTH: float = 2.0          # asset line width

TITLE_FONTSIZE:  int = 15
LABEL_FONTSIZE:  int = 11
TICK_FONTSIZE:   int = 9
LEGEND_FONTSIZE: int = 9

# High-contrast professional colour palette (WCAG contrast-safe on dark bg)
PALETTE: List[str] = [
    "#00bfff",   # Deep Sky Blue  — AAPL
    "#39ff14",   # Neon Green     — GOOGL
    "#ff6b35",   # Vivid Orange   — TSLA
    "#ff3cac",   # Hot Pink       — MSFT
    "#ffe600",   # Vivid Yellow   — AMZN
]

FIGURE_SIZE: tuple[int, int] = (13, 6)   # (width, height) in inches
FIGURE_DPI:  int = 150                   # output resolution


# ──────────────────────────────────────────────────────────────────────────────
# PortfolioAnalyst
# ──────────────────────────────────────────────────────────────────────────────

class PortfolioAnalyst:
    """
    Downloads historical prices and computes professional risk/return metrics
    for a set of equity tickers over a given lookback period.

    Parameters
    ----------
    tickers : List[str]
        Yahoo Finance ticker symbols to analyse.
    period : str
        Lookback string accepted by yfinance (e.g. '2y', '1y', '6mo').
    risk_free_rate : float
        Annual risk-free rate for Sharpe / Sortino calculations.
    benchmark : str
        Market proxy ticker for Beta computation (default: 'SPY').
    """

    def __init__(
        self,
        tickers: List[str],
        period: str = "2y",
        risk_free_rate: float = RISK_FREE_RATE,
        benchmark: str = BENCHMARK_TICKER,
    ) -> None:
        self.tickers: List[str] = tickers
        self.period: str = period
        self.risk_free_rate: float = risk_free_rate
        self.benchmark: str = benchmark

        self.prices: pd.DataFrame = pd.DataFrame()
        self.benchmark_prices: pd.Series = pd.Series(dtype=float)
        self.log_returns: pd.DataFrame = pd.DataFrame()
        self.benchmark_returns: pd.Series = pd.Series(dtype=float)
        self.cov_matrix: pd.DataFrame = pd.DataFrame()

        self.metrics: Dict[str, Dict[str, float]] = {}
        self.weights: pd.Series = pd.Series(dtype=float)

        self._download()
        self._compute_returns()

    # ──────────────────────────────────────────────────────────────────────────
    # Data acquisition
    # ──────────────────────────────────────────────────────────────────────────

    def _download(self) -> None:
        """
        Download adjusted-close prices via yfinance.

        Compatible with both MultiIndex layouts produced by different
        yfinance releases:
          - Field-first  (< 0.2.50):  columns = (Field, Ticker)
          - Ticker-first (>= 0.2.50): columns = (Ticker, Field)
        """
        all_tickers: List[str] = self.tickers + [self.benchmark]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw: pd.DataFrame = yf.download(
                all_tickers,
                period=self.period,
                auto_adjust=True,
                progress=False,
            )

        if raw.empty:
            raise RuntimeError(
                "yfinance returned an empty DataFrame. "
                "Check your internet connection or ticker symbols."
            )

        prices: pd.DataFrame
        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = raw.columns.get_level_values(0).unique().tolist()
            lvl1 = raw.columns.get_level_values(1).unique().tolist()

            if "Close" in lvl0:                       # field-first layout
                prices = raw["Close"]
            elif "Close" in lvl1:                     # ticker-first layout
                prices = raw.xs("Close", axis=1, level=1)
            else:
                raise ValueError(
                    f"'Close' not found in MultiIndex columns.\n"
                    f"  level-0: {lvl0}\n  level-1: {lvl1}"
                )
        else:
            prices = raw[["Close"]] if "Close" in raw.columns else raw

        print(f"  ✔ Downloaded {len(prices)} trading days for {all_tickers}")

        self.benchmark_prices = prices[self.benchmark].dropna()
        self.prices           = prices[self.tickers].dropna()

    # ──────────────────────────────────────────────────────────────────────────
    # Return & covariance computation
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_returns(self) -> None:
        """Compute daily log-returns and the annualised covariance matrix."""
        self.log_returns = np.log(self.prices / self.prices.shift(1)).dropna()
        self.benchmark_returns = np.log(
            self.benchmark_prices / self.benchmark_prices.shift(1)
        ).dropna()
        self.cov_matrix = self.log_returns.cov() * TRADING_DAYS

    # ──────────────────────────────────────────────────────────────────────────
    # Risk / return metrics
    # ──────────────────────────────────────────────────────────────────────────

    def sharpe_ratio(self, ticker: str) -> float:
        """
        Annualised Sharpe Ratio.

            SR = (Rp − Rf) / σp
        """
        r   = self.log_returns[ticker]
        rp  = r.mean() * TRADING_DAYS
        vol = r.std()  * np.sqrt(TRADING_DAYS)
        return np.nan if vol == 0 else (rp - self.risk_free_rate) / vol

    def sortino_ratio(self, ticker: str) -> float:
        """
        Annualised Sortino Ratio.

            Sortino = (Rp − Rf) / σd

        σd uses only the subset of negative daily returns.
        """
        r   = self.log_returns[ticker]
        rp  = r.mean() * TRADING_DAYS
        std = r[r < 0].std() * np.sqrt(TRADING_DAYS)
        return np.nan if (std == 0 or np.isnan(std)) else (rp - self.risk_free_rate) / std

    def beta(self, ticker: str) -> float:
        """
        CAPM Beta relative to benchmark.

            β = Cov(Rp, Rm) / Var(Rm)
        """
        aligned = pd.concat(
            [self.log_returns[ticker], self.benchmark_returns], axis=1
        ).dropna()
        aligned.columns = ["asset", "market"]
        cov   = np.cov(aligned["asset"], aligned["market"])
        var_m = cov[1, 1]
        return np.nan if var_m == 0 else cov[0, 1] / var_m

    def maximum_drawdown(self, ticker: str) -> float:
        """
        Maximum Drawdown (MDD).

            MDD = (Trough − Peak) / Peak   → always ≤ 0
        """
        cumulative  = (1 + self.log_returns[ticker]).cumprod()
        rolling_max = cumulative.cummax()
        drawdown    = (cumulative - rolling_max) / rolling_max
        return float(drawdown.min())

    def _drawdown_series(self, ticker: str) -> pd.Series:
        """Return the full drawdown time-series for a given ticker."""
        cumulative  = (1 + self.log_returns[ticker]).cumprod()
        rolling_max = cumulative.cummax()
        return (cumulative - rolling_max) / rolling_max

    # ──────────────────────────────────────────────────────────────────────────
    # Portfolio optimisation
    # ──────────────────────────────────────────────────────────────────────────

    def minimum_variance_weights(self) -> pd.Series:
        """
        Inverse-variance heuristic weights.

            w_i = (1/σ_i²) / Σ(1/σ_j²)

        A closed-form approximation to Markowitz that avoids noisy
        expected-return estimates.
        """
        variances: pd.Series = pd.Series(
            np.diag(self.cov_matrix.values),
            index=self.cov_matrix.index,
        )
        inv_var = 1.0 / variances
        return (inv_var / inv_var.sum()).round(4)

    # ──────────────────────────────────────────────────────────────────────────
    # Reporting
    # ──────────────────────────────────────────────────────────────────────────

    def run(self) -> Dict[str, Dict[str, float]]:
        """Compute all metrics for every ticker and print a formatted report."""
        sep = "═" * 62
        thin = "─" * 62

        print(f"\n{sep}")
        print("  PORTFOLIO ANALYST  —  Quantitative Metrics Report")
        print(sep)

        for ticker in self.tickers:
            sr  = self.sharpe_ratio(ticker)
            srt = self.sortino_ratio(ticker)
            b   = self.beta(ticker)
            mdd = self.maximum_drawdown(ticker)

            self.metrics[ticker] = {
                "Sharpe Ratio": sr,
                "Sortino Ratio": srt,
                "Beta": b,
                "Max Drawdown (%)": mdd * 100,
            }

            print(f"\n  {ticker}")
            print(f"    {'Sharpe Ratio':<26}: {sr:>8.4f}")
            print(f"    {'Sortino Ratio':<26}: {srt:>8.4f}")
            print(f"    {'Beta (vs ' + self.benchmark + ')':<26}: {b:>8.4f}")
            print(f"    {'Max Drawdown':<26}: {mdd * 100:>7.2f} %")

        self.weights = self.minimum_variance_weights()

        print(f"\n{thin}")
        print("  Suggested Weights  (Inverse-Variance Heuristic)")
        print(thin)
        for ticker, w in self.weights.items():
            bar = "█" * int(w * 40)
            print(f"    {ticker:<8}: {w * 100:>5.2f} %  {bar}")

        print(f"{sep}\n")
        return self.metrics

    # ──────────────────────────────────────────────────────────────────────────
    # Bloomberg Terminal design system
    # ──────────────────────────────────────────────────────────────────────────

    def _create_figure(self, title: str) -> tuple[Figure, Axes]:
        """
        Initialise a figure and axes with the Bloomberg Terminal dark style.

        Design rules applied here:
        - Figure background  : BG_FIGURE (#121212)
        - Axes background    : BG_AXES   (#1a1a1a)
        - Spines top + right : hidden
        - Spines bottom+left : visible, muted colour
        - Grid               : dotted, GRID_ALPHA=0.15, white
        - Ticks              : outward, muted colour
        """
        fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)

        # ── Backgrounds ───────────────────────────────────────────────────────
        fig.patch.set_facecolor(BG_FIGURE)
        ax.set_facecolor(BG_AXES)

        # ── Title ─────────────────────────────────────────────────────────────
        ax.set_title(
            title,
            color=CLR_TITLE,
            fontsize=TITLE_FONTSIZE,
            fontweight="bold",
            pad=16,
            loc="left",          # Bloomberg aligns titles left
        )

        # ── Spines — remove top & right; style bottom & left ─────────────────
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color(CLR_SPINE)
        ax.spines["bottom"].set_linewidth(0.8)
        ax.spines["left"].set_color(CLR_SPINE)
        ax.spines["left"].set_linewidth(0.8)

        # ── Grid — subtle, punteada, baja opacidad ────────────────────────────
        ax.grid(
            True,
            color=CLR_GRID,
            linestyle=GRID_STYLE,
            linewidth=0.5,
            alpha=GRID_ALPHA,
        )
        ax.set_axisbelow(True)   # grid behind data lines

        # ── Ticks ─────────────────────────────────────────────────────────────
        ax.tick_params(
            colors=CLR_LABEL,
            labelsize=TICK_FONTSIZE,
            direction="out",
            length=4,
            width=0.6,
        )

        # ── Axis labels ───────────────────────────────────────────────────────
        ax.set_xlabel("Date", color=CLR_LABEL, fontsize=LABEL_FONTSIZE, labelpad=8)

        return fig, ax

    def _style_legend(self, ax: Axes) -> None:
        """Apply terminal-style formatting to the legend."""
        legend = ax.legend(
            facecolor="#1e1e1e",
            edgecolor="#333333",
            labelcolor=CLR_TITLE,
            fontsize=LEGEND_FONTSIZE,
            framealpha=0.85,
            loc="upper left",
        )
        for line in legend.get_lines():
            line.set_linewidth(2.5)

    # ──────────────────────────────────────────────────────────────────────────
    # Visualisations
    # ──────────────────────────────────────────────────────────────────────────

    def plot_cumulative_returns(
        self,
        save_path: Optional[str] = None,
        show: bool = True,
    ) -> None:
        """
        Chart 1 — Cumulative compounded returns.

            CR_t = ∏(1 + r_i) − 1   for i = 1 … t
        """
        cum_returns: pd.DataFrame = (
            (1 + self.log_returns).cumprod() - 1
        ) * 100   # as percentage

        fig, ax = self._create_figure("Cumulative Returns")

        for i, ticker in enumerate(cum_returns.columns):
            ax.plot(
                cum_returns.index,
                cum_returns[ticker],
                label=ticker,
                color=PALETTE[i % len(PALETTE)],
                linewidth=LINE_WIDTH,
                zorder=3,
            )

        ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
        ax.set_ylabel("Return (%)", color=CLR_LABEL, fontsize=LABEL_FONTSIZE, labelpad=8)
        ax.axhline(0, color=CLR_ZERO, linewidth=0.8, linestyle="-", zorder=2)

        self._style_legend(ax)
        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=FIGURE_DPI, bbox_inches="tight",
                        facecolor=BG_FIGURE)
            print(f"  ✔ Saved → {save_path}")
        if show:
            plt.show()
        plt.close(fig)

    def plot_drawdown(
        self,
        save_path: Optional[str] = None,
        show: bool = True,
    ) -> None:
        """
        Chart 2 — Historical drawdown per asset.

            DD_t = (Cumulative_t − Peak_t) / Peak_t   → always ≤ 0
        """
        fig, ax = self._create_figure("Historical Drawdown")

        for i, ticker in enumerate(self.tickers):
            dd = self._drawdown_series(ticker) * 100   # as percentage
            color = PALETTE[i % len(PALETTE)]

            ax.fill_between(dd.index, dd, 0,
                            alpha=0.12, color=color, zorder=2)
            ax.plot(dd.index, dd,
                    label=ticker, color=color,
                    linewidth=LINE_WIDTH, zorder=3)

        ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
        ax.set_ylabel("Drawdown (%)", color=CLR_LABEL, fontsize=LABEL_FONTSIZE, labelpad=8)
        ax.axhline(0, color=CLR_ZERO, linewidth=0.8, linestyle="-", zorder=2)

        self._style_legend(ax)
        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=FIGURE_DPI, bbox_inches="tight",
                        facecolor=BG_FIGURE)
            print(f"  ✔ Saved → {save_path}")
        if show:
            plt.show()
        plt.close(fig)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    TICKERS: List[str] = ["AAPL", "GOOGL", "TSLA", "MSFT", "AMZN"]

    analyst = PortfolioAnalyst(
        tickers=TICKERS,
        period="2y",
        risk_free_rate=RISK_FREE_RATE,
        benchmark=BENCHMARK_TICKER,
    )

    analyst.run()

    analyst.plot_cumulative_returns(save_path="cumulative_returns.png", show=True)
    analyst.plot_drawdown(save_path="drawdown.png", show=True)
