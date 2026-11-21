# Portfolio-Lab
# Portfolio Lab
### Quantitative Portfolio Analytics, Performance Evaluation & Risk Assessment

Portfolio Lab is a Python-based desktop application designed to analyse investment portfolios through quantitative finance, statistical analysis, and financial data visualisation. It provides tools to evaluate historical portfolio performance, measure investment risk, assess diversification, and compare results against market benchmarks.

The project combines financial mathematics with software engineering to make portfolio analytics accessible through an interactive desktop interface.

## Key Features

- **Portfolio Construction:** Configure portfolio holdings, asset allocations, benchmark indices, analysis periods, and risk-free rates.
- **Performance Analysis:** Evaluate historical returns, compound annual growth rate (CAGR), and portfolio growth over time.
- **Risk Assessment:** Calculate volatility, maximum drawdown, Value at Risk (VaR), and Conditional Value at Risk (CVaR).
- **Risk-Adjusted Performance:** Analyse Sharpe and Sortino ratios to assess returns relative to risk.
- **Diversification Analysis:** Examine asset correlations and portfolio-level risk contributions.
- **Benchmark Comparison:** Compare portfolio performance and risk metrics against a selected market benchmark.
- **Data Visualisation:** Generate performance charts, drawdown plots, rolling risk metrics, and correlation visualisations.
- **Portfolio Management:** Import holdings from CSV files and save portfolio configurations locally.
- **Desktop Interface:** Use an interactive PySide6 GUI with background processing for analysis tasks.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application and analytical logic |
| PySide6 | Desktop graphical interface |
| pandas | Financial time-series processing |
| NumPy | Numerical calculations |
| SciPy | Statistical analysis |
| Matplotlib | Financial data visualisation |
| yfinance | Historical market-data retrieval |

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/Portfolio-Lab.git
cd Portfolio-Lab
```

Replace `YOUR-USERNAME` with your GitHub username.

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install numpy pandas scipy matplotlib yfinance PySide6
```

### 4. Run the application

Run the main Python file from the repository directory:

```bash
python portfolio_lab.py
```

Replace `portfolio_lab.py` with the actual filename of the application entry point if it differs.

## Quantitative Methodology

Portfolio Lab applies established quantitative finance techniques to historical market data.

| Metric | Purpose |
|---|---|
| CAGR | Measures annualised portfolio growth |
| Volatility | Measures variability in returns |
| Sharpe Ratio | Evaluates excess return relative to total volatility |
| Sortino Ratio | Evaluates excess return relative to downside deviation |
| Maximum Drawdown | Measures the largest peak-to-trough decline |
| VaR | Estimates potential losses at a specified confidence level |
| CVaR | Estimates the average loss beyond the VaR threshold |
| Correlation | Measures the relationship between asset returns |

These metrics provide complementary perspectives on portfolio performance and risk. Results depend on the selected assets, historical period, data quality, and model assumptions.

## Project Objectives

- Apply quantitative finance concepts to practical portfolio analysis.
- Develop a reusable financial analytics application using Python.
- Explore the relationship between investment performance, risk, and diversification.
- Translate financial data into interpretable metrics and visualisations.
- Strengthen skills in statistical computing, data analysis, and financial software development.

## Limitations

Portfolio Lab analyses historical data and estimates risk using quantitative models. Historical performance does not guarantee future results. Market-data availability, missing observations, transaction costs, taxes, liquidity constraints, and model assumptions can affect the interpretation of results.

The application is intended for educational and analytical purposes and should not be treated as personalised investment advice.

## Author

**Essa Asim**

Developed as an independent project exploring the intersection of quantitative finance, Python development, and portfolio risk analysis.

## Disclaimer

This project is for educational and research purposes only. It does not constitute financial, investment, or trading advice.
