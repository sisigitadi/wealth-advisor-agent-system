# Wealth Advisor Assistant

Technical assessment submission by Sigit Adi Irianto.

A mini multi-agent system that reviews client portfolios, flags anomalies, and generates prioritized advisory recommendations.

## a. Architecture Design

Coordinated by `WealthAdvisorOrchestrator` across three specialized agents and a tool layer:

- **`DataFetcherAgent`**: Pulls client profile, portfolio, transactions, and market indicators through tool wrappers (`CRMTool`, `PortfolioTool`, `TransactionFeedTool`, `MarketDataTool`).
- **`AnalyzerAgent`**: Checks for liquidity deficits (cash < target), allocation drift (equities > risk cap), and transaction anomalies using z-scores.
- **`AdvisoryAgent`**: Converts detected risks into prioritized recommendations (Outreach, Rebalancing, Realignment, Hedging).
- **`Memory`**: Handles session state in-memory and persists run summaries to `wealth_advisor_memory.json` to detect multi-session trends.

## b. Agent Interactions and Flow

1. Orchestrator triggers `DataFetcherAgent` with the client ID.
2. Ingested data passes to `AnalyzerAgent` for risk calculation and anomaly scoring.
3. If high-severity flags or anomalies exist, execution pauses at `_human_checkpoint` for operator confirmation (can be bypassed with `--auto`).
4. `AdvisoryAgent` receives the analysis and client history, then formulates action items.
5. Orchestrator saves the run summary to memory and prints the final JSON dossier.

## c. Key Decisions & Trade-offs

- **Standard library only**: No external runtime packages needed. Easy to run anywhere without dependency issues.
- **stderr for logs, stdout for JSON**: Lets you pipe clean output directly (`python wealth_advisor_agent.py --auto > output.json`) while still seeing execution logs in the terminal.
- **Graceful degradation**: CRM and portfolio are required, but missing market or transaction data won't crash the review.
- **Statistical z-score for anomalies**: Flags unusual outflows relative to each client's spending pattern rather than relying only on fixed dollar limits.

## d. Assumptions Made

- Client data represents Indonesian HNWI clients (`Budi Santoso` in Jakarta, `Dewi Lestari` in Surabaya) with USD-denominated accounts.
- Small transaction batches are used as a demonstration; production would use rolling multi-month data.
- The human checkpoint uses terminal prompts (`[y/N]`); in production this would be a Slack prompt or web UI.
- Local JSON file is used to simulate database persistence.

## e. Instructions to Run the Project

```bash
# Optional: virtual environment
python -m venv venv

# Activate venv:
# Windows (PowerShell): .\venv\Scripts\Activate.ps1
# Windows (CMD):        venv\Scripts\activate.bat
# Linux / macOS:        source venv/bin/activate

# Install test dependencies (pytest)
python -m pip install -r requirements.txt

# Run interactive review (prompts for operator approval)
python wealth_advisor_agent.py

# Run automated review (auto-approves)
python wealth_advisor_agent.py --auto

# Target another client
python wealth_advisor_agent.py CLIENT_1002 --auto

# Run tests
python -m pytest test_wealth_advisor.py -v
```
