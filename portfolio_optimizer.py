"""
Portfolio Lab - single-file version (desktop app, pure Python)
===============================================================
Opens a welcome window; press "Open Portfolio Lab" to launch the analysis window.
Analyse how a portfolio behaves as a whole: return, risk, drawdowns, correlations,
and which holdings carry most of the risk. Prices come from Yahoo Finance.
For education only. Not financial advice.

Install once:   python -m pip install PySide6 numpy pandas scipy matplotlib yfinance
Run:            python portfolio_lab.py          (or press F5 in VS Code)

Yahoo symbols: AAPL, HBL.KA, RELIANCE.NS, BTC-USD, EURUSD=X, GBPUSD=X, GC=F (gold futures).
Linux only: if the window will not open (an "xcb" error), run  sudo apt install libxcb-cursor0

The Portfolio Lab logo is embedded in this file (LOGO_B64 near the bottom), so no image file is needed.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

# Tell matplotlib to use PySide6 (must be set before matplotlib's Qt backend is imported)
os.environ.setdefault("QT_API", "pyside6")

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QColor, QFontDatabase, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog, QFormLayout, QFrame,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)
from scipy import stats


# ============================================================================
# THEME
# ============================================================================
PALETTES = {
    "light": dict(BG="#f4f6f8", CARD="#ffffff", TEXT="#1f2933", MUTED="#6b7785", BORDER="#d7dde4",
                  BLUE="#2563eb", ORANGE="#f59e0b", RED="#dc2626", GREEN="#16a34a",
                  BTN="#2563eb", BTN_ACTIVE="#1d4ed8", TAB="#e3e8ee"),
    "dark": dict(BG="#0b1220", CARD="#162032", TEXT="#e5e7eb", MUTED="#9aa7b8", BORDER="#2a3a52",
                 BLUE="#60a5fa", ORANGE="#fbbf24", RED="#f87171", GREEN="#4ade80",
                 BTN="#2563eb", BTN_ACTIVE="#1d4ed8", TAB="#1d2a40"),
}

C = {}          # the current colours; charts and widgets read from here
current = "light"


def set_theme(name: str):
    """Switch the colours in C and the matplotlib defaults."""
    global current
    current = name
    C.clear()
    C.update(PALETTES[name])
    matplotlib.rcParams.update({
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "grid.color": C["MUTED"],
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.labelsize": 9, "font.size": 9,
        "figure.facecolor": C["CARD"], "axes.facecolor": C["CARD"], "savefig.facecolor": C["CARD"],
        "axes.edgecolor": C["MUTED"], "axes.labelcolor": C["TEXT"], "axes.titlecolor": C["TEXT"],
        "text.color": C["TEXT"], "xtick.color": C["TEXT"], "ytick.color": C["TEXT"],
        "legend.labelcolor": C["TEXT"],
    })


def qt_palette():
    """A QPalette for the current theme (imported here so charts can be tested without Qt)."""
    from PySide6.QtGui import QColor, QPalette

    R, G = QPalette.ColorRole, QPalette.ColorGroup
    pal = QPalette()
    pairs = {
        R.Window: C["BG"], R.WindowText: C["TEXT"], R.Base: C["CARD"], R.AlternateBase: C["TAB"],
        R.Text: C["TEXT"], R.Button: C["TAB"], R.ButtonText: C["TEXT"], R.ToolTipBase: C["CARD"],
        R.ToolTipText: C["TEXT"], R.PlaceholderText: C["MUTED"], R.Highlight: C["BTN"],
        R.HighlightedText: "#ffffff", R.Link: C["BLUE"],
    }
    for role, colour in pairs.items():
        pal.setColor(role, QColor(colour))
    for role in (R.Text, R.ButtonText, R.WindowText):
        pal.setColor(G.Disabled, role, QColor(C["MUTED"]))
    return pal


def stylesheet() -> str:
    """Extra styling for the headline cards, the Analyse button and the tabs."""
    return f"""
    QFrame#card {{ background:{C['CARD']}; border:1px solid {C['BORDER']}; border-radius:6px; }}
    QLabel#cardTitle {{ color:{C['MUTED']}; font-size:11px; background:transparent; }}
    QLabel#cardValue {{ font-size:22px; font-weight:bold; background:transparent; }}
    QLabel#cardSub {{ color:{C['MUTED']}; font-size:11px; background:transparent; }}
    QLabel#muted {{ color:{C['MUTED']}; }}
    QPushButton#go {{ background:{C['BTN']}; color:white; font-weight:bold; padding:8px 14px;
                      border:none; border-radius:4px; }}
    QPushButton#go:hover {{ background:{C['BTN_ACTIVE']}; }}
    QPushButton#go:disabled {{ background:{C['MUTED']}; color:#e5e7eb; }}
    QTableWidget {{ gridline-color:{C['BORDER']}; border:1px solid {C['BORDER']}; }}
    QHeaderView::section {{ background:{C['TAB']}; color:{C['TEXT']}; padding:4px; border:none;
                            border-right:1px solid {C['BORDER']}; }}
    QTabWidget::pane {{ border:1px solid {C['BORDER']}; background:{C['CARD']}; }}
    QTabBar::tab {{ background:{C['TAB']}; color:{C['MUTED']}; padding:7px 16px; }}
    QTabBar::tab:selected {{ background:{C['CARD']}; color:{C['TEXT']}; }}
    QPlainTextEdit {{ background:{C['CARD']}; color:{C['TEXT']}; border:none; }}
    """


set_theme("light")

theme = SimpleNamespace(C=C, set_theme=set_theme, qt_palette=qt_palette, stylesheet=stylesheet)


# ============================================================================
# PORTFOLIO MODEL
# ============================================================================
PERIODS = ["1y", "2y", "3y", "5y", "10y", "max"]
REBALANCE_MODES = {
    "daily": "Rebalance daily (constant weights)",
    "none": "Buy and hold",
}


@dataclass
class Portfolio:
    holdings: dict = field(default_factory=dict)   # ticker -> weight, as typed (any positive scale)
    name: str = "Untitled portfolio"
    benchmark: str = "SPY"
    period: str = "5y"
    risk_free: float = 4.0                         # percent per year
    rebalance: str = "daily"                       # "daily" or "none"

    def __post_init__(self):
        cleaned = {}
        for ticker, weight in self.holdings.items():
            t = str(ticker).strip().upper()
            if t:
                cleaned[t] = cleaned.get(t, 0.0) + float(weight)   # duplicates are added together
        self.holdings = cleaned
        self.benchmark = (self.benchmark or "").strip().upper()

    def weights(self) -> pd.Series:
        """Weights scaled to add up to 1 (so 50/30/20 and 5/3/2 mean the same thing)."""
        if not self.holdings:
            raise ValueError("The portfolio has no holdings. Add at least one ticker.")
        s = pd.Series(self.holdings, dtype=float)
        if (s <= 0).any():
            raise ValueError("Every weight must be a positive number.")
        return s / s.sum()

    # ---- saving and loading
    def save(self, path):
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Portfolio":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            raise ValueError(f"Could not read that file: {err}") from err
        if not isinstance(data, dict) or not isinstance(data.get("holdings"), dict):
            raise ValueError("That file is not a Portfolio Lab portfolio.")
        defaults = cls()
        return cls(
            holdings=data["holdings"],
            name=data.get("name", defaults.name),
            benchmark=data.get("benchmark", defaults.benchmark),
            period=data.get("period", defaults.period) if data.get("period") in PERIODS else defaults.period,
            risk_free=float(data.get("risk_free", defaults.risk_free)),
            rebalance=data.get("rebalance", defaults.rebalance) if data.get("rebalance") in REBALANCE_MODES
            else defaults.rebalance,
        )


def holdings_from_csv(path) -> dict:
    """Read a broker-style CSV. Needs a ticker/symbol column; a weight/value/amount column is optional
    (without one, every holding gets the same weight). Dollar signs, commas and % signs are ignored."""
    try:
        df = pd.read_csv(path)
    except Exception as err:
        raise ValueError(f"Could not read that CSV: {err}") from err
    df.columns = [str(c).strip().lower() for c in df.columns]

    ticker_col = next((c for c in ("ticker", "symbol", "tickers") if c in df.columns), None)
    if ticker_col is None:
        raise ValueError("The CSV needs a column named 'ticker' or 'symbol'.")
    weight_col = next((c for c in ("weight", "weight %", "weight (%)", "allocation", "value", "market value",
                                   "amount") if c in df.columns), None)

    out = {}
    for i, row in df.iterrows():
        t = str(row[ticker_col]).strip().upper()
        if not t or t == "NAN":
            continue
        if weight_col is None:
            w = 1.0
        else:
            cleaned = "".join(ch for ch in str(row[weight_col]) if ch.isdigit() or ch in ".-")
            try:
                w = float(cleaned)
            except ValueError:
                continue
        if w > 0:
            out[t] = out.get(t, 0.0) + w
    if not out:
        raise ValueError("No usable rows found in that CSV.")
    return out


# ============================================================================
# PRICE DATA AND CACHE
# ============================================================================
CACHE_DIR = Path.home() / ".portfolio_lab" / "cache"
MAX_AGE_SECONDS = 12 * 3600      # cached prices older than this are refreshed
MIN_DAYS = 60                    # fewer trading days than this is not enough to analyse


class DataError(Exception):
    """Raised when prices can't be loaded or there isn't enough of them."""


def _cache_file(ticker: str, period: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", ticker)
    return CACHE_DIR / f"{safe}__{period}.csv"


def _download(ticker: str, period: str) -> pd.Series:
    import yfinance as yf          # imported here so the rest of the package works (and tests run) without it

    hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if hist is None or hist.empty or "Close" not in hist:
        return pd.Series(dtype=float)
    prices = hist["Close"].dropna()
    prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
    prices = prices[~prices.index.duplicated(keep="last")]
    return prices.astype(float).rename(ticker)


def _read_cache(path: Path, ticker: str) -> pd.Series:
    try:
        s = pd.read_csv(path, index_col=0, parse_dates=True)["price"]
        return s.astype(float).rename(ticker)
    except Exception:
        return pd.Series(dtype=float)


def load_prices(ticker: str, period: str = "5y", use_cache: bool = True) -> pd.Series:
    """Adjusted closing prices for one ticker. Uses the cache when it is fresh, and falls back to
    older cached data if the download fails (for example when offline). Empty Series if nothing works."""
    path = _cache_file(ticker, period)
    if use_cache and path.exists() and (time.time() - path.stat().st_mtime) < MAX_AGE_SECONDS:
        cached = _read_cache(path, ticker)
        if len(cached) > 0:
            return cached

    try:
        prices = _download(ticker, period)
    except Exception:
        prices = pd.Series(dtype=float)

    if prices.empty:
        return _read_cache(path, ticker) if path.exists() else prices

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        prices.rename("price").to_csv(path, header=True)
    except OSError:
        pass                         # a cache that can't be written is not worth failing over
    return prices


def load_price_table(tickers, period="5y", progress=None):
    """Prices for several tickers on a shared set of dates.

    Returns (table, failed, notes). The table only keeps dates where every ticker has a price (short gaps,
    such as different market holidays, are filled forward first). `failed` lists tickers with no usable data.
    """
    say = progress or (lambda msg: None)
    series, failed, notes = {}, [], []
    for i, t in enumerate(tickers, 1):
        say(f"Loading {t} ({i}/{len(tickers)})...")
        s = load_prices(t, period)
        if len(s) < MIN_DAYS:
            failed.append(t)
        else:
            series[t] = s
    if not series:
        return pd.DataFrame(), failed, notes

    table = pd.concat(series, axis=1).sort_index()
    starts = table.apply(lambda col: col.first_valid_index())
    earliest, latest, limiting = starts.min(), starts.max(), starts.idxmax()
    table = table.ffill(limit=3).dropna()
    if (latest - earliest).days > 30:
        notes.append(f"History starts {latest.date()} because {limiting} has no earlier data.")
    return table, failed, notes


# ============================================================================
# MATHS
# ============================================================================
TRADING_DAYS = 252


def asset_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna()


def portfolio_returns(rets: pd.DataFrame, weights: pd.Series, rebalance: str = "daily") -> pd.Series:
    """Daily portfolio returns.

    "daily": weights are reset to the targets every day (constant weights).
    "none":  buy and hold. Start with the weights, then let each holding drift with its own price.
    """
    w = weights.reindex(rets.columns)
    if rebalance == "none":
        value = (1 + rets).cumprod().mul(w, axis=1).sum(axis=1)
        start = pd.Series([1.0], index=[rets.index[0] - pd.Timedelta(days=1)])
        out = pd.concat([start, value]).pct_change().dropna()
    else:
        out = rets.mul(w, axis=1).sum(axis=1)
    out.name = "Portfolio"
    return out


def wealth_curve(r: pd.Series) -> pd.Series:
    """Growth of 1 unit, starting at exactly 1.0 the day before the first return."""
    start = pd.Series([1.0], index=[r.index[0] - pd.Timedelta(days=1)])
    return pd.concat([start, (1 + r).cumprod()])


def drawdown_series(r: pd.Series) -> pd.Series:
    w = wealth_curve(r)
    return w / w.cummax() - 1.0


def risk_contributions(rets: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Each holding's share of total portfolio volatility (adds up to 1.0).

    A holding's share = its weight x how much it moves with the rest of the portfolio, divided by
    portfolio volatility. A volatile or highly correlated holding can have a big share with a small weight.
    """
    cov = rets.cov().values * TRADING_DAYS
    w = weights.reindex(rets.columns).values
    port_vol = np.sqrt(w @ cov @ w)
    if port_vol == 0:
        return pd.Series(np.nan, index=rets.columns)
    marginal = cov @ w / port_vol
    return pd.Series(w * marginal / port_vol, index=rets.columns)


def _years(r) -> float:
    return (r.index[-1] - r.index[0]).days / 365.25


def asset_table(rets: pd.DataFrame, weights: pd.Series, rf: float) -> pd.DataFrame:
    """One row per holding: weight, annual return, volatility, Sharpe, and share of portfolio risk."""
    n_years = _years(rets)
    ex = rets - rf / TRADING_DAYS
    t = pd.DataFrame(index=rets.columns)
    t["weight"] = weights.reindex(rets.columns)
    t["cagr"] = (1 + rets).prod() ** (1 / n_years) - 1
    t["vol"] = rets.std(ddof=1) * np.sqrt(TRADING_DAYS)
    t["sharpe"] = ex.mean() / ex.std(ddof=1) * np.sqrt(TRADING_DAYS)
    t["risk_share"] = risk_contributions(rets, weights)
    return t.sort_values("risk_share", ascending=False)


def compute_metrics(port: pd.Series, bench: pd.Series | None, rf: float,
                    rets: pd.DataFrame, weights: pd.Series) -> dict:
    n_years = _years(port)
    rf_d = rf / TRADING_DAYS
    ex = port - rf_d

    cagr = (1 + port).prod() ** (1 / n_years) - 1 if n_years > 0 else np.nan
    vol_d = port.std(ddof=1)
    sharpe = ex.mean() / ex.std(ddof=1) * np.sqrt(TRADING_DAYS) if ex.std() > 0 else np.nan
    downside = np.sqrt(np.mean(np.minimum(ex, 0.0) ** 2))
    sortino = ex.mean() / downside * np.sqrt(TRADING_DAYS) if downside > 0 else np.nan
    max_dd = drawdown_series(port).min()
    q5, q1 = np.percentile(port, 5), np.percentile(port, 1)
    jb_p = stats.jarque_bera(port)[1]

    # Diversification: how much risk is removed by holding things together
    w = weights.reindex(rets.columns).values
    asset_vols = rets.std(ddof=1).values * np.sqrt(TRADING_DAYS)
    port_vol = vol_d * np.sqrt(TRADING_DAYS)
    n = len(w)
    corr = rets.corr().values
    avg_corr = (corr.sum() - n) / (n * (n - 1)) if n > 1 else np.nan

    m = {
        "n_days": len(port), "n_years": n_years,
        "total_return": (1 + port).prod() - 1, "cagr": cagr, "ann_vol": port_vol,
        "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd,
        "calmar": cagr / abs(max_dd) if max_dd < 0 else np.nan,
        "var95": -q5, "var99": -q1,
        "cvar95": -port[port <= q5].mean(), "cvar99": -port[port <= q1].mean(),
        "skew": stats.skew(port), "kurt": stats.kurtosis(port), "jb_p": jb_p,
        "best_day": port.max(), "worst_day": port.min(), "up_days": (port > 0).mean(),
        "div_ratio": (w @ asset_vols) / port_vol if port_vol > 0 else np.nan,
        "eff_n": 1.0 / np.sum(w ** 2),
        "avg_corr": avg_corr,
        "beta": np.nan, "alpha": np.nan, "corr": np.nan, "r2": np.nan,
        "tracking_error": np.nan, "info_ratio": np.nan,
    }

    if bench is not None:
        both = pd.concat([port, bench], axis=1, join="inner").dropna()
        both.columns = ["p", "b"]
        if len(both) > 30 and both["b"].var() > 0:
            beta = both["p"].cov(both["b"]) / both["b"].var()
            alpha = ((both["p"] - rf_d).mean() - beta * (both["b"] - rf_d).mean()) * TRADING_DAYS
            c = both["p"].corr(both["b"])
            active = both["p"] - both["b"]
            te = active.std(ddof=1) * np.sqrt(TRADING_DAYS)
            m.update(beta=beta, alpha=alpha, corr=c, r2=c ** 2, tracking_error=te,
                     info_ratio=active.mean() * TRADING_DAYS / te if te > 0 else np.nan)
    return m

mx = SimpleNamespace(TRADING_DAYS=TRADING_DAYS, asset_returns=asset_returns,
                    portfolio_returns=portfolio_returns, wealth_curve=wealth_curve,
                    drawdown_series=drawdown_series, risk_contributions=risk_contributions,
                    asset_table=asset_table, compute_metrics=compute_metrics)


# ============================================================================
# ANALYSIS PIPELINE
# ============================================================================
@dataclass
class Analysis:
    portfolio: Portfolio
    weights: pd.Series
    prices: pd.DataFrame
    asset_rets: pd.DataFrame
    port_rets: pd.Series
    bench_rets: pd.Series | None
    metrics: dict
    corr: pd.DataFrame
    table: pd.DataFrame
    rf: float
    notes: list = field(default_factory=list)

    @property
    def bench_ticker(self) -> str:
        return self.portfolio.benchmark


def run_analysis(portfolio: Portfolio, progress=None) -> Analysis:
    say = progress or (lambda msg: None)
    weights = portfolio.weights()
    rf = portfolio.risk_free / 100.0

    prices, failed, notes = load_price_table(list(weights.index), portfolio.period, say)
    if failed:
        raise DataError("No usable data for: " + ", ".join(failed) + ". Check the symbols and your internet "
                        "connection (examples: AAPL, MSFT, HBL.KA, RELIANCE.NS).")
    if len(prices) < MIN_DAYS:
        raise DataError(f"Only {len(prices)} shared trading days across these holdings. Try a longer History "
                        "or remove the newest holding.")

    rets = mx.asset_returns(prices)
    port = mx.portfolio_returns(rets, weights, portfolio.rebalance)

    bench = None
    if portfolio.benchmark:
        say(f"Loading benchmark {portfolio.benchmark}...")
        b = load_prices(portfolio.benchmark, portfolio.period)
        if len(b) >= MIN_DAYS:
            aligned = b.reindex(prices.index.union(b.index)).ffill().reindex(prices.index)
            br = aligned.pct_change().dropna().reindex(port.index).dropna()
            if len(br) > 30:
                bench = br
        if bench is None:
            notes.append(f"Benchmark '{portfolio.benchmark}' not found, so beta and alpha are skipped.")

    say("Calculating...")
    m = mx.compute_metrics(port, bench, rf, rets, weights)
    if portfolio.rebalance == "none":
        notes.append("Risk shares use the starting weights.")
    return Analysis(portfolio=portfolio, weights=weights, prices=prices, asset_rets=rets, port_rets=port,
                    bench_rets=bench, metrics=m, corr=rets.corr(), table=mx.asset_table(rets, weights, rf),
                    rf=rf, notes=notes)


# ============================================================================
# FORMATTING AND TEXT REPORT
# ============================================================================
def pct(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def num(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def sharpe_verdict(s):
    if s is None or not np.isfinite(s):
        return ""
    if s < 0:
        return "Poor"
    if s < 0.5:
        return "Weak"
    if s < 1:
        return "Acceptable"
    if s < 2:
        return "Good"
    return "Excellent"


def details_text(a: Analysis) -> str:
    m, p = a.metrics, a.portfolio
    first, last = a.port_rets.index[0].date(), a.port_rets.index[-1].date()
    rows = [
        f"{p.name}",
        f"{first} to {last}  |  {m['n_days']} trading days  |  {m['n_years']:.1f} years",
        f"Risk-free rate {a.rf * 100:.2f}%  |  {REBALANCE_MODES.get(p.rebalance, p.rebalance)}",
        "",
        "HOLDINGS",
        f"  {'Ticker':<10}{'Weight':>9}{'Return/yr':>11}{'Volatility':>12}{'Sharpe':>9}{'Risk share':>12}",
    ]
    for t, r in a.table.iterrows():
        rows.append(f"  {t:<10}{pct(r['weight'], 1):>9}{pct(r['cagr'], 1):>11}{pct(r['vol'], 1):>12}"
                    f"{num(r['sharpe']):>9}{pct(r['risk_share'], 1):>12}")
    rows += [
        "",
        "RETURNS",
        f"  Total return                         {pct(m['total_return'])}",
        f"  Annualised return (CAGR)             {pct(m['cagr'])}",
        f"  Best day / worst day                 {pct(m['best_day'])} / {pct(m['worst_day'])}",
        f"  Days up                              {pct(m['up_days'], 1)}",
        "",
        "RISK-ADJUSTED PERFORMANCE",
        f"  Annualised volatility                {pct(m['ann_vol'])}",
        f"  Sharpe ratio                         {num(m['sharpe'])}",
        f"  Sortino ratio                        {num(m['sortino'])}",
        f"  Calmar ratio                         {num(m['calmar'])}",
        f"  Maximum drawdown                     {pct(m['max_dd'])}",
        "",
        "DIVERSIFICATION",
        f"  Diversification ratio                {num(m['div_ratio'])}   (1.00 = no benefit)",
        f"  Effective number of holdings         {num(m['eff_n'], 1)}   (of {len(a.weights)})",
        f"  Average pairwise correlation         {num(m['avg_corr'])}",
        "",
        "TAIL RISK (one day, historical)",
        f"  Value at Risk 95% / 99%              {pct(m['var95'])} / {pct(m['var99'])}",
        f"  Expected Shortfall 95% / 99%         {pct(m['cvar95'])} / {pct(m['cvar99'])}",
        "",
        f"VERSUS {a.bench_ticker or 'BENCHMARK'}",
        f"  Beta                                 {num(m['beta'])}",
        f"  Alpha (annual, Jensen)               {pct(m['alpha'])}",
        f"  Correlation / R-squared              {num(m['corr'])} / {num(m['r2'])}",
        f"  Tracking error / information ratio   {pct(m['tracking_error'])} / {num(m['info_ratio'])}",
        "",
        "DISTRIBUTION",
        f"  Skewness / excess kurtosis           {num(m['skew'])} / {num(m['kurt'])}",
        f"  Jarque-Bera p-value                  {num(m['jb_p'], 4)}  "
        f"({'returns are not normal' if m['jb_p'] < 0.05 else 'consistent with normal'})",
    ]
    if a.notes:
        rows += ["", "NOTES"] + [f"  - {n}" for n in a.notes]
    rows += ["", "Past performance does not predict future results.", "For education only, not financial advice."]
    return "\n".join(rows)


# ============================================================================
# CHARTS
# ============================================================================
ROLL = 63   # rolling window: about three months of trading days


def fig_overview(a: Analysis) -> Figure:
    fig = Figure(figsize=(10, 6), layout="constrained")
    gs = fig.add_gridspec(2, 1, height_ratios=[1.7, 1])

    ax = fig.add_subplot(gs[0])
    cmap = matplotlib.colormaps["tab10"]
    if len(a.asset_rets.columns) > 1:
        for i, t in enumerate(a.asset_rets.columns):
            ax.plot(mx.wealth_curve(a.asset_rets[t]), lw=0.9, alpha=0.5, color=cmap(i % 10), label=t)
    ax.plot(mx.wealth_curve(a.port_rets), color=C["BLUE"], lw=2.4, label="Portfolio")
    if a.bench_rets is not None:
        ax.plot(mx.wealth_curve(a.bench_rets), color=C["ORANGE"], lw=1.8, ls="--", label=a.bench_ticker)
    ax.set_title("Growth of 1 unit invested")
    ax.legend(frameon=False, loc="upper left", ncol=min(4, len(ax.get_lines())), fontsize=8)

    ax = fig.add_subplot(gs[1])
    dd = mx.drawdown_series(a.port_rets) * 100
    ax.fill_between(dd.index, dd, 0, color=C["RED"], alpha=0.45, label="Portfolio")
    if a.bench_rets is not None:
        ax.plot(mx.drawdown_series(a.bench_rets) * 100, color=C["ORANGE"], lw=1.2, label=a.bench_ticker)
        ax.legend(frameon=False, loc="lower left", fontsize=8)
    ax.set_title("Drawdown from peak (%)")
    return fig


def fig_correlation(a: Analysis) -> Figure:
    fig = Figure(figsize=(8, 6), layout="constrained")
    ax = fig.add_subplot(111)
    corr = a.corr
    n = len(corr)
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(n), corr.columns, rotation=45, ha="right")
    ax.set_yticks(range(n), corr.index)
    ax.grid(False)
    for i in range(n):
        for j in range(n):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9 if n <= 8 else 7,
                    color="white" if abs(v) > 0.6 else C["TEXT"])
    fig.colorbar(im, ax=ax, shrink=0.8)
    avg = a.metrics["avg_corr"]
    sub = f"  |  average pairwise: {avg:.2f}" if np.isfinite(avg) else ""
    ax.set_title(f"Correlation of daily returns{sub}")
    return fig


def fig_risk(a: Analysis) -> Figure:
    fig = Figure(figsize=(10, 6), layout="constrained")
    gs = fig.add_gridspec(2, 2)
    m = a.metrics

    # Share of money vs share of risk
    ax = fig.add_subplot(gs[0, 0])
    t = a.table
    x = np.arange(len(t))
    ax.bar(x - 0.2, t["weight"] * 100, 0.4, color=C["BLUE"], label="Share of money")
    ax.bar(x + 0.2, t["risk_share"] * 100, 0.4, color=C["ORANGE"], label="Share of risk")
    ax.set_xticks(x, t.index, rotation=45 if len(t) > 6 else 0)
    ax.set_title("Where your money is vs where your risk is (%)")
    ax.legend(frameon=False, fontsize=8)

    # Return distribution
    ax = fig.add_subplot(gs[0, 1])
    ax.hist(a.port_rets * 100, bins=60, color=C["BLUE"], alpha=0.7)
    ax.axvline(-m["var95"] * 100, color=C["ORANGE"], ls="--", label=f"VaR 95%: {pct(m['var95'])}")
    ax.axvline(-m["cvar95"] * 100, color=C["RED"], ls="--", label=f"Shortfall 95%: {pct(m['cvar95'])}")
    ax.set_title("Daily portfolio returns (%)")
    ax.legend(frameon=False, fontsize=8)

    # Rolling volatility
    ax = fig.add_subplot(gs[1, :])
    if len(a.port_rets) > ROLL + 5:
        scale = np.sqrt(mx.TRADING_DAYS) * 100
        ax.plot(a.port_rets.rolling(ROLL).std() * scale, color=C["BLUE"], lw=1.8, label="Portfolio")
        if a.bench_rets is not None:
            ax.plot(a.bench_rets.rolling(ROLL).std() * scale, color=C["ORANGE"], lw=1.3, ls="--",
                    label=a.bench_ticker)
        ax.legend(frameon=False, fontsize=8)
    ax.set_title("Rolling 3-month volatility (annualised %)")
    return fig

charts = SimpleNamespace(fig_overview=fig_overview, fig_correlation=fig_correlation, fig_risk=fig_risk)


# ============================================================================
# BACKGROUND WORKER
# ============================================================================
class TaskSignals(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    """Run fn(*args, progress=<callable>) on a pool thread and report back with signals."""

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = TaskSignals()
        self.setAutoDelete(False)       # the window keeps a reference, so the signals outlive run()

    def run(self):
        try:
            result = self.fn(*self.args, progress=self.signals.progress.emit)
        except Exception as err:
            self.signals.failed.emit(str(err) or err.__class__.__name__)
            return
        self.signals.finished.emit(result)


# ============================================================================
# CHART TAB
# ============================================================================
class ChartTab(QWidget):
    def __init__(self, placeholder=""):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self.canvas = None
        self.toolbar = None
        self.message = QLabel(placeholder)
        self.message.setObjectName("muted")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet("font-size: 14px;")
        self._layout.addWidget(self.message)

    def show_message(self, text):
        self._drop_figure()
        self.message.setText(text)
        self.message.setVisible(True)

    def show_figure(self, fig):
        self._drop_figure()
        self.message.setVisible(False)
        self.canvas = FigureCanvasQTAgg(fig)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self._layout.addWidget(self.toolbar)
        self._layout.addWidget(self.canvas, 1)

    def _drop_figure(self):
        for w in (self.toolbar, self.canvas):
            if w is not None:
                self._layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
        self.canvas = self.toolbar = None


# ============================================================================
# HOLDINGS TABLE
# ============================================================================
ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class HoldingsPanel(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._loading = False

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Ticker", "Weight"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)

        self.add_btn = QPushButton("Add")
        self.remove_btn = QPushButton("Remove")
        self.equal_btn = QPushButton("Equal weight")
        self.import_btn = QPushButton("Import CSV...")
        self.add_btn.clicked.connect(lambda: self.add_row(focus=True))
        self.remove_btn.clicked.connect(self.remove_selected)
        self.equal_btn.clicked.connect(self.equal_weight)

        row1 = QHBoxLayout()
        row1.addWidget(self.add_btn)
        row1.addWidget(self.remove_btn)
        row1.addWidget(self.equal_btn)
        row2 = QHBoxLayout()
        row2.addWidget(self.import_btn)
        row2.addStretch(1)

        self.total_label = QLabel("")
        self.total_label.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.total_label)
        self._update_total()

    # ---- editing
    def add_row(self, ticker="", weight="", focus=False):
        self._loading = True
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(ticker))
        w = QTableWidgetItem(str(weight))
        w.setTextAlignment(ALIGN_RIGHT)
        self.table.setItem(r, 1, w)
        self._loading = False
        if focus:
            self.table.setCurrentCell(r, 0)
            self.table.editItem(self.table.item(r, 0))
        self._update_total()

    def remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        for r in rows:
            self.table.removeRow(r)
        self._update_total()
        self.changed.emit()

    def equal_weight(self):
        rows = [r for r in range(self.table.rowCount()) if self._text(r, 0)]
        if not rows:
            return
        self._loading = True
        for r in rows:
            self.table.item(r, 1).setText(f"{100 / len(rows):.2f}")
        self._loading = False
        self._update_total()
        self.changed.emit()

    def set_holdings(self, holdings: dict):
        self._loading = True
        self.table.setRowCount(0)
        self._loading = False
        for ticker, weight in holdings.items():
            self.add_row(ticker, f"{weight:g}")
        self._update_total()
        self.changed.emit()

    def get_holdings(self) -> dict:
        """Read the table. Raises ValueError with a friendly message if something is wrong."""
        out = {}
        for r in range(self.table.rowCount()):
            ticker, text = self._text(r, 0).upper(), self._text(r, 1)
            if not ticker and not text:
                continue                                  # blank row
            if not ticker:
                raise ValueError(f"Row {r + 1} has a weight but no ticker.")
            try:
                weight = float(text.replace("%", "").replace(",", ""))
            except ValueError:
                raise ValueError(f"The weight for {ticker} must be a number, for example 25.") from None
            if weight <= 0:
                raise ValueError(f"The weight for {ticker} must be greater than zero.")
            if ticker in out:
                raise ValueError(f"{ticker} appears twice. Combine the rows into one.")
            out[ticker] = weight
        if not out:
            raise ValueError("Add at least one holding (ticker and weight).")
        return out

    # ---- helpers
    def _text(self, row, col) -> str:
        item = self.table.item(row, col)
        return item.text().strip() if item else ""

    def _on_item_changed(self, _item):
        if not self._loading:
            self._update_total()
            self.changed.emit()

    def _update_total(self):
        total = 0.0
        for r in range(self.table.rowCount()):
            try:
                total += float(self._text(r, 1).replace("%", "").replace(",", ""))
            except ValueError:
                pass
        self.total_label.setText(f"Total: {total:g}   (weights are scaled to 100% automatically)")


# ============================================================================
# MAIN WINDOW
# ============================================================================
DEFAULT_HOLDINGS = {"AAPL": 25, "MSFT": 25, "JNJ": 20, "XOM": 15, "GLD": 15}
JSON_FILTER = "Portfolio files (*.json)"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("PortfolioLab", "PortfolioLab")
        self.analysis: Analysis | None = None
        self.path: Path | None = None            # the file the portfolio was opened from / saved to
        self.name = "Untitled portfolio"
        self.status_kind = "muted"
        self._task = None
        self.resize(1320, 840)
        self.setMinimumSize(1000, 680)

        self._build_menus()
        self._build_ui()
        self._build_status_bar()

        self.apply_portfolio(Portfolio(holdings=DEFAULT_HOLDINGS))
        self.dark_action.setChecked(self.settings.value("dark", False, type=bool))
        self.apply_theme()
        self.set_status("Edit your holdings, then press Analyse (F5).")
        self.update_title()

    # ================================================================ building the window
    def _build_menus(self):
        def act(text, slot, shortcut=None, checkable=False):
            a = QAction(text, self)
            a.setCheckable(checkable)
            if shortcut is not None:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            return a

        S = QKeySequence.StandardKey
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(act("&New", self.new_portfolio, S.New))
        file_menu.addAction(act("&Open portfolio...", self.open_portfolio, S.Open))
        file_menu.addAction(act("&Save", self.save_portfolio, S.Save))
        file_menu.addAction(act("Save &as...", self.save_portfolio_as, S.SaveAs))
        file_menu.addSeparator()
        file_menu.addAction(act("&Import holdings from CSV...", self.import_csv))
        file_menu.addSeparator()
        file_menu.addAction(act("&Quit", self.close, S.Quit))

        run_menu = self.menuBar().addMenu("&Analysis")
        run_menu.addAction(act("&Run analysis", self.start_analysis, "F5"))

        view_menu = self.menuBar().addMenu("&View")
        self.dark_action = act("&Dark mode", self.toggle_dark, checkable=True)
        view_menu.addAction(self.dark_action)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(act("&About", self.show_about))

    def _build_ui(self):
        # ---- left: inputs
        self.holdings = HoldingsPanel()
        self.holdings.import_btn.clicked.connect(self.import_csv)
        hold_box = QGroupBox("Holdings")
        QVBoxLayout(hold_box).addWidget(self.holdings)

        self.bench_edit = QLineEdit()
        self.period_combo = QComboBox()
        self.period_combo.addItems(PERIODS)
        self.rf_edit = QLineEdit()
        self.mode_combo = QComboBox()
        for key, label in REBALANCE_MODES.items():
            self.mode_combo.addItem(label, key)
        form_box = QGroupBox("Settings")
        form = QFormLayout(form_box)
        form.addRow("Benchmark", self.bench_edit)
        form.addRow("History", self.period_combo)
        form.addRow("Risk-free rate (%)", self.rf_edit)
        form.addRow("Weighting", self.mode_combo)
        self.bench_edit.returnPressed.connect(self.start_analysis)
        self.rf_edit.returnPressed.connect(self.start_analysis)

        self.go_btn = QPushButton("Analyse")
        self.go_btn.setObjectName("go")
        self.go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.go_btn.clicked.connect(self.start_analysis)

        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(10, 10, 6, 10)
        lay.addWidget(hold_box, 1)
        lay.addWidget(form_box)
        lay.addWidget(self.go_btn)

        # ---- right: cards + tabs
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(6, 10, 10, 10)
        rlay.addLayout(self._build_cards())

        self.tabs = QTabWidget()
        self.overview_tab = ChartTab("Press Analyse to see results.")
        self.corr_tab = ChartTab("Press Analyse to see results.")
        self.risk_tab = ChartTab("Press Analyse to see results.")
        self.table_tab = QTableWidget(0, 6)
        self.table_tab.setHorizontalHeaderLabels(
            ["Ticker", "Weight", "Return / year", "Volatility", "Sharpe", "Share of risk"])
        self.table_tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_tab.verticalHeader().setVisible(False)
        self.table_tab.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        for widget, title in [(self.overview_tab, "Overview"), (self.corr_tab, "Correlation"),
                              (self.risk_tab, "Risk"), (self.table_tab, "Holdings"),
                              (self.details, "All numbers")]:
            self.tabs.addTab(widget, title)
        rlay.addWidget(self.tabs, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 980])
        self.setCentralWidget(splitter)

    def _build_cards(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        self.cards = {}
        for key, title in [("cagr", "Annual return"), ("vol", "Volatility"), ("sharpe", "Sharpe ratio"),
                           ("dd", "Max drawdown"), ("beta", "Beta"), ("div", "Diversification")]:
            frame = QFrame()
            frame.setObjectName("card")
            box = QVBoxLayout(frame)
            box.setContentsMargins(12, 8, 12, 8)
            box.setSpacing(0)
            t, v, s = QLabel(title), QLabel("-"), QLabel(" ")
            t.setObjectName("cardTitle")
            v.setObjectName("cardValue")
            s.setObjectName("cardSub")
            for w in (t, v, s):
                box.addWidget(w)
            row.addWidget(frame, 1)
            self.cards[key] = (v, s)
        return row

    def _build_status_bar(self):
        self.status = QLabel("")
        self.statusBar().addWidget(self.status, 1)
        disclaimer = QLabel("For education only. Not financial advice.")
        disclaimer.setObjectName("muted")
        self.statusBar().addPermanentWidget(disclaimer)

    # ================================================================ theme
    def toggle_dark(self):
        self.settings.setValue("dark", self.dark_action.isChecked())
        self.apply_theme()

    def apply_theme(self):
        theme.set_theme("dark" if self.dark_action.isChecked() else "light")
        QApplication.instance().setPalette(theme.qt_palette())
        self.setStyleSheet(theme.stylesheet())
        self.set_status(self.status.text(), self.status_kind)
        if self.analysis is not None:
            self.render(self.analysis)               # redraw charts in the new colours
        else:
            for v, _ in self.cards.values():
                v.setStyleSheet(f"color:{theme.C['TEXT']};")

    def status_colour(self, kind):
        return {"red": theme.C["RED"], "orange": theme.C["ORANGE"]}.get(kind, theme.C["MUTED"])

    def set_status(self, text, kind="muted"):
        self.status_kind = kind
        self.status.setText(text)
        self.status.setStyleSheet(f"color:{self.status_colour(kind)};")

    # ================================================================ portfolio <-> widgets
    def current_portfolio(self) -> Portfolio:
        holdings = self.holdings.get_holdings()
        try:
            rf = float(self.rf_edit.text().replace("%", "").strip() or "0")
        except ValueError:
            raise ValueError("The risk-free rate must be a number, for example 4.0.") from None
        return Portfolio(holdings=holdings, name=self.name, benchmark=self.bench_edit.text(),
                         period=self.period_combo.currentText(), risk_free=rf,
                         rebalance=self.mode_combo.currentData())

    def apply_portfolio(self, p: Portfolio):
        self.name = p.name
        self.holdings.set_holdings(p.holdings)
        self.bench_edit.setText(p.benchmark)
        self.period_combo.setCurrentText(p.period)
        self.rf_edit.setText(f"{p.risk_free:g}")
        self.mode_combo.setCurrentIndex(max(self.mode_combo.findData(p.rebalance), 0))

    def update_title(self):
        self.setWindowTitle(f"{self.name} - Portfolio Lab")

    # ================================================================ file actions
    def new_portfolio(self):
        self.path, self.analysis = None, None
        self.apply_portfolio(Portfolio(holdings=DEFAULT_HOLDINGS))
        for tab in (self.overview_tab, self.corr_tab, self.risk_tab):
            tab.show_message("Press Analyse to see results.")
        self.table_tab.setRowCount(0)
        self.details.setPlainText("")
        for v, s in self.cards.values():
            v.setText("-")
            s.setText(" ")
        self.update_title()
        self.set_status("New portfolio.")

    def open_portfolio(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open portfolio", "", JSON_FILTER)
        if not path:
            return
        try:
            p = Portfolio.load(path)
        except ValueError as err:
            QMessageBox.warning(self, "Could not open", str(err))
            return
        self.path = Path(path)
        p.name = p.name if p.name != "Untitled portfolio" else self.path.stem
        self.apply_portfolio(p)
        self.update_title()
        self.set_status(f"Opened {self.path.name}.")

    def save_portfolio(self):
        if self.path is None:
            self.save_portfolio_as()
            return
        self._write(self.path)

    def save_portfolio_as(self):
        suggested = (self.name if self.name != "Untitled portfolio" else "my_portfolio") + ".json"
        path, _ = QFileDialog.getSaveFileName(self, "Save portfolio", suggested, JSON_FILTER)
        if not path:
            return
        path = Path(path)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        self.name = path.stem
        self._write(path)

    def _write(self, path: Path):
        try:
            self.current_portfolio().save(path)
        except ValueError as err:
            self.set_status(str(err), "red")
            return
        except OSError as err:
            QMessageBox.warning(self, "Could not save", str(err))
            return
        self.path = path
        self.update_title()
        self.set_status(f"Saved {path.name}.")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import holdings", "", "CSV files (*.csv)")
        if not path:
            return
        try:
            holdings = holdings_from_csv(path)
        except ValueError as err:
            QMessageBox.warning(self, "Could not import", str(err))
            return
        self.holdings.set_holdings(holdings)
        self.set_status(f"Imported {len(holdings)} holdings from {Path(path).name}.")

    def show_about(self):
        QMessageBox.about(
            self, "About Portfolio Lab",
            "<b>Portfolio Lab</b><br>Portfolio risk and diversification analysis.<br><br>"
            "Prices come from Yahoo Finance via yfinance. For education only. Not financial advice. "
            "Past performance does not predict future results.")

    # ================================================================ running an analysis
    def start_analysis(self):
        if not self.go_btn.isEnabled():
            return
        try:
            portfolio = self.current_portfolio()
        except ValueError as err:
            self.set_status(str(err), "red")
            return
        self.go_btn.setEnabled(False)
        self.set_status("Starting...")
        task = Task(run_analysis, portfolio)
        task.signals.progress.connect(self.on_progress)
        task.signals.finished.connect(self.on_finished)
        task.signals.failed.connect(self.on_failed)
        self._task = task                             # keep it alive until it reports back
        QThreadPool.globalInstance().start(task)

    def on_progress(self, message):
        self.set_status(message)

    def on_failed(self, message):
        self.go_btn.setEnabled(True)
        self.set_status(message, "red")
        if self.analysis is None:
            self.overview_tab.show_message(message)

    def on_finished(self, analysis: Analysis):
        self.go_btn.setEnabled(True)
        try:
            self.analysis = analysis
            self.render(analysis)
        except Exception as err:                      # a drawing bug should not crash the app
            self.set_status(f"Could not draw results: {err}", "red")
            return
        p = analysis.portfolio
        first, last = analysis.port_rets.index[0].date(), analysis.port_rets.index[-1].date()
        note = " ".join(analysis.notes)
        self.set_status(note or f"{len(analysis.weights)} holdings, {first} to {last}",
                        "orange" if note else "muted")

    # ================================================================ showing results
    def render(self, a: Analysis):
        C, m = theme.C, a.metrics

        def card(key, value, sub=" ", colour=None):
            v, s = self.cards[key]
            v.setText(value)
            v.setStyleSheet(f"color:{colour or C['TEXT']};")
            s.setText(sub)

        sh = m["sharpe"]
        card("cagr", pct(m["cagr"], 1), f"total {pct(m['total_return'], 0)}")
        card("vol", pct(m["ann_vol"], 1), f"{m['n_years']:.1f} years of data")
        card("sharpe", num(sh), sharpe_verdict(sh),
             C["GREEN"] if sh == sh and sh >= 1 else (C["RED"] if sh == sh and sh < 0 else None))
        card("dd", pct(m["max_dd"], 1), "worst peak to trough", C["RED"])
        card("beta", num(m["beta"]), f"vs {a.bench_ticker}" if a.bench_rets is not None else "no benchmark")
        card("div", num(m["div_ratio"]), f"{m['eff_n']:.1f} effective holdings")

        self.overview_tab.show_figure(charts.fig_overview(a))
        self.corr_tab.show_figure(charts.fig_correlation(a))
        self.risk_tab.show_figure(charts.fig_risk(a))
        self.fill_holdings_table(a)
        self.details.setPlainText(details_text(a))

    def fill_holdings_table(self, a: Analysis):
        t = a.table
        self.table_tab.setRowCount(len(t))
        for r, (ticker, row) in enumerate(t.iterrows()):
            cells = [ticker, pct(row["weight"], 1), pct(row["cagr"], 1), pct(row["vol"], 1),
                     num(row["sharpe"]), pct(row["risk_share"], 1)]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 5 and row["risk_share"] - row["weight"] > 0.05:
                    item.setForeground(QColor(theme.C["ORANGE"]))      # carries much more risk than money
                self.table_tab.setItem(r, c, item)


# ============================================================================
# WELCOME WINDOW
# ============================================================================
# Colours taken from the logo: warm cream background, deep navy lettering.
W_CREAM = "#f5eee4"
W_NAVY = "#0c1527"
W_NAVY_HOVER = "#1c2b4a"
W_NAVY_PRESS = "#050a14"
W_TAGLINE = "#5a6478"
W_DIM = "#8a8f9a"


class WelcomeWindow(QWidget):
    """Full-screen start page: the Portfolio Lab logo and a button that opens the program.

    Esc or F11 switches between full screen and a normal window. The Quit link closes everything.
    """
    open_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Portfolio Lab")
        self.setObjectName("welcome")
        self.setMinimumSize(640, 500)
        self.setStyleSheet(f"""
            QWidget#welcome {{ background:{W_CREAM}; }}
            QLabel {{ background:transparent; }}
            QLabel#tagline {{ color:{W_TAGLINE}; font-size:17px; font-style:italic; }}
            QLabel#fine {{ color:{W_DIM}; font-size:12px; }}
            QPushButton#launch {{ background:{W_NAVY}; color:{W_CREAM}; font-size:17px; font-weight:bold;
                                  padding:15px 44px; border:none; border-radius:8px; }}
            QPushButton#launch:hover {{ background:{W_NAVY_HOVER}; }}
            QPushButton#launch:pressed {{ background:{W_NAVY_PRESS}; }}
            QPushButton#quit {{ background:transparent; color:{W_DIM}; border:none; font-size:12px;
                                text-decoration:underline; padding:4px; }}
            QPushButton#quit:hover {{ color:{W_NAVY}; }}
        """)

        self.logo_source = QPixmap()
        self.logo_source.loadFromData(base64.b64decode("".join(LOGO_B64.split())))

        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline = QLabel("Understand how your portfolio really behaves")
        tagline.setObjectName("tagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.launch_btn = QPushButton("Open Portfolio Lab")
        self.launch_btn.setObjectName("launch")
        self.launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_btn.clicked.connect(self.open_requested)

        self.hint = QLabel("Esc: leave full screen")
        self.hint.setObjectName("fine")
        disclaimer = QLabel("For education only. Not financial advice.")
        disclaimer.setObjectName("fine")
        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("quit")
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.clicked.connect(self.close)

        bottom = QHBoxLayout()
        bottom.addWidget(self.hint, 1, Qt.AlignmentFlag.AlignLeft)
        bottom.addWidget(disclaimer, 1, Qt.AlignmentFlag.AlignCenter)
        bottom.addWidget(quit_btn, 1, Qt.AlignmentFlag.AlignRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.addStretch(5)
        layout.addWidget(self.logo)
        layout.addSpacing(10)
        layout.addWidget(tagline)
        layout.addSpacing(44)
        layout.addWidget(self.launch_btn, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(6)
        layout.addLayout(bottom)

        for key in ("Return", "Enter"):
            QShortcut(QKeySequence(key), self, activated=self.open_requested.emit)
        QShortcut(QKeySequence("Escape"), self, activated=lambda: self.set_fullscreen(False))
        QShortcut(QKeySequence("F11"), self, activated=lambda: self.set_fullscreen(not self.isFullScreen()))
        self.launch_btn.setFocus()

    def resizeEvent(self, event):
        """Keep the logo at about 55% of the window width (between 320 and 900 px)."""
        super().resizeEvent(event)
        width = int(min(max(self.width() * 0.55, 320), 900))
        self.logo.setPixmap(self.logo_source.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation))

    def set_fullscreen(self, on: bool):
        if on:
            self.showFullScreen()
            self.hint.setText("Esc: leave full screen")
        else:
            self.showNormal()
            self.resize(900, 620)
            screen = self.screen().availableGeometry()
            self.move(screen.center().x() - 450, max(screen.center().y() - 360, 0))
            self.hint.setText("F11: full screen")


# ============================================================================
# EMBEDDED LOGO (transparent PNG, navy on clear)
# ============================================================================
LOGO_B64 = """
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
"""


# ============================================================================
# START
# ============================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Portfolio Lab")
    app.setOrganizationName("PortfolioLab")

    welcome = WelcomeWindow()
    windows = {}                                      # keeps the main window alive

    def open_main():
        window = MainWindow()
        windows["main"] = window
        window.show()
        welcome.close()                               # the main window is already open, so the app keeps running

    welcome.open_requested.connect(open_main)
    welcome.set_fullscreen(True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()