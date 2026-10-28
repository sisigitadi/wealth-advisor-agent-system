"""Wealth Advisor Assistant - lightweight multi-agent system."""

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

# Logs go to stderr so stdout remains clean for piping JSON
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("wealth_advisor")


# Client data with Indonesian identity & location, evaluated in USD
CRM_DATA = {
    "CLIENT_1001": {
        "client_id": "CLIENT_1001",
        "name": "Budi Santoso",
        "location": "Jakarta, Indonesia",
        "risk_profile": "Moderate",
        "target_liquidity": 25000.0,
        "investment_goals": "Capital Preservation & Long-Term Growth",
        "tenure_years": 4,
    },
    "CLIENT_1002": {
        "client_id": "CLIENT_1002",
        "name": "Dewi Lestari",
        "location": "Surabaya, Indonesia",
        "risk_profile": "Aggressive",
        "target_liquidity": 10000.0,
        "investment_goals": "High Growth Tech & Emerging Markets",
        "tenure_years": 1,
    },
}

PORTFOLIO_DATA = {
    "CLIENT_1001": {
        "cash_balance": 18500.0,
        "equities_value": 310000.0,
        "fixed_income_value": 180000.0,
        "alternative_assets": 45000.0,
        "total_aum": 553500.0,
    },
    "CLIENT_1002": {
        "cash_balance": 8200.0,
        "equities_value": 420000.0,
        "fixed_income_value": 30000.0,
        "alternative_assets": 95000.0,
        "total_aum": 553200.0,
    },
}

TRANSACTION_DATA = {
    "CLIENT_1001": [
        {"tx_id": "TX_901", "date": "2026-10-01", "type": "dividend", "amount": 1250.0, "category": "Passive Income Dividend"},
        {"tx_id": "TX_902", "date": "2026-10-10", "type": "investment", "amount": 5000.0, "category": "Fixed Income Treasury"},
        {"tx_id": "TX_903", "date": "2026-10-18", "type": "withdrawal", "amount": 42000.0, "category": "Uncategorized Wire Transfer"},
        {"tx_id": "TX_904", "date": "2026-10-24", "type": "fee", "amount": 120.0, "category": "Custodian Account Fee"},
    ],
    "CLIENT_1002": [
        {"tx_id": "TX_801", "date": "2026-10-03", "type": "investment", "amount": 75000.0, "category": "Tech ETF"},
        {"tx_id": "TX_802", "date": "2026-10-05", "type": "investment", "amount": 80000.0, "category": "Global Tech Fund"},
        {"tx_id": "TX_803", "date": "2026-10-12", "type": "withdrawal", "amount": 3000.0, "category": "Personal Withdrawal"},
        {"tx_id": "TX_804", "date": "2026-10-20", "type": "investment", "amount": 60000.0, "category": "Bluechip Tech Equity"},
    ],
}

MARKET_DATA = {
    "SP500": {"current": 5890.5, "ytd_return_pct": 12.3},
    "US10Y_YIELD": 4.35,
    "VIX": {"current": 22.8, "elevated": True},
}


# Tool Abstraction
class CRMTool:
    def run(self, client_id: str) -> Dict[str, Any]:
        if client_id not in CRM_DATA:
            raise KeyError(f"Client '{client_id}' not found in CRM.")
        return CRM_DATA[client_id]


class PortfolioTool:
    def run(self, client_id: str) -> Dict[str, Any]:
        if client_id not in PORTFOLIO_DATA:
            raise KeyError(f"Portfolio data for '{client_id}' not available.")
        return PORTFOLIO_DATA[client_id]


class TransactionFeedTool:
    def run(self, client_id: str) -> List[Dict[str, Any]]:
        return TRANSACTION_DATA.get(client_id, [])


class MarketDataTool:
    def run(self) -> Dict[str, Any]:
        return MARKET_DATA


# Memory: in-memory session cache + persistent json storage
class Memory:
    def __init__(self, storage_path: str = "wealth_advisor_memory.json"):
        self.storage_path = os.path.normpath(storage_path)
        self.session: Dict[str, Any] = {}
        self.history: Dict[str, List[Dict[str, Any]]] = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load memory file ({e}), starting fresh")
        return {}

    def save_history(self, client_id: str, summary: Dict[str, Any]):
        key = f"history:{client_id}"
        self.history.setdefault(key, []).append(summary)
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to persist history: {e}")

    def get_client_history(self, client_id: str) -> List[Dict[str, Any]]:
        return self.history.get(f"history:{client_id}", [])


# Agents
class DataFetcherAgent:
    """Ingests client profile, portfolio, transactions, and market context."""

    def __init__(self, tools: Dict[str, Any]):
        self.tools = tools

    def run(self, client_id: str) -> Dict[str, Any]:
        logger.info(f"DataFetcher: fetching data for {client_id}")

        profile = self.tools["crm_api"].run(client_id)
        portfolio = self.tools["portfolio_api"].run(client_id)

        # Optional data sources degrade gracefully
        transactions = []
        try:
            transactions = self.tools["transaction_feed"].run(client_id)
        except Exception as e:
            logger.warning(f"DataFetcher: transactions unavailable ({e})")

        market = {}
        try:
            market = self.tools["market_data"].run()
        except Exception as e:
            logger.warning(f"DataFetcher: market data unavailable ({e})")

        return {
            "profile": profile,
            "portfolio": portfolio,
            "transactions": transactions,
            "market": market,
        }


class AnalyzerAgent:
    """Evaluates portfolio risk: liquidity deficit, allocation drift, and transaction outliers."""

    EQUITY_CAPS = {
        "Conservative": 30.0,
        "Moderate": 50.0,
        "Aggressive": 75.0,
    }

    LARGE_WITHDRAWAL_THRESHOLD = 20000.0
    RAPID_INVESTMENT_THRESHOLD = 100000.0

    def run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Analyzer: evaluating portfolio risk and anomalies")

        profile = data["profile"]
        portfolio = data["portfolio"]
        transactions = data.get("transactions", [])
        market = data.get("market", {})

        anomalies = []
        risk_flags = []

        # 1. Liquidity buffer check
        cash = portfolio.get("cash_balance", 0.0)
        target_liq = profile.get("target_liquidity", 0.0)
        liquidity_status = "ADEQUATE"

        if cash < target_liq:
            liquidity_status = "DEFICIT"
            deficit = target_liq - cash
            risk_flags.append({
                "severity": "HIGH",
                "risk_type": "LIQUIDITY_DEFICIT",
                "detail": f"Cash balance (${cash:,.2f}) is ${deficit:,.2f} below target reserve (${target_liq:,.2f}).",
            })

        # 2. Transaction anomaly detection (z-score + absolute threshold)
        if transactions:
            amounts = [t["amount"] for t in transactions]
            n = len(amounts)
            mean = sum(amounts) / n
            variance = sum((x - mean) ** 2 for x in amounts) / (n - 1) if n > 1 else 0.0
            stdev = math.sqrt(variance)

            for tx in transactions:
                reasons = []
                severity = "MEDIUM"
                z = (tx["amount"] - mean) / stdev if stdev > 0 else 0.0

                if abs(z) >= 1.5:
                    reasons.append(f"Statistical outlier (z={z:+.2f})")

                if tx["type"] == "withdrawal" and tx["amount"] >= self.LARGE_WITHDRAWAL_THRESHOLD:
                    reasons.append(f"Large uncategorized capital outflow (${tx['amount']:,.2f})")
                    severity = "CRITICAL"

                if reasons:
                    anomalies.append({
                        "tx_id": tx["tx_id"],
                        "date": tx["date"],
                        "type": tx["type"],
                        "amount": tx["amount"],
                        "severity": severity,
                        "reasons": reasons,
                    })

            # Check rapid capital deployment
            invested = sum(t["amount"] for t in transactions if t["type"] == "investment")
            if invested >= self.RAPID_INVESTMENT_THRESHOLD:
                risk_flags.append({
                    "severity": "MEDIUM",
                    "risk_type": "RAPID_CAPITAL_DEPLOYMENT",
                    "detail": f"${invested:,.2f} invested rapidly within short observation window.",
                })

        # 3. Portfolio drift check
        total_aum = portfolio.get("total_aum", 0.0)
        equities = portfolio.get("equities_value", 0.0)
        equity_pct = round((equities / total_aum * 100), 2) if total_aum > 0 else 0.0
        cap = self.EQUITY_CAPS.get(profile.get("risk_profile", "Moderate"), 50.0)

        if equity_pct > cap:
            risk_flags.append({
                "severity": "MEDIUM",
                "risk_type": "PORTFOLIO_DRIFT",
                "detail": f"Equity exposure ({equity_pct}%) exceeds {profile.get('risk_profile')} cap ({cap}%).",
            })

        # 4. Volatility amplification
        vix = market.get("VIX", {})
        if vix.get("elevated") and any(f["severity"] == "HIGH" for f in risk_flags):
            risk_flags.append({
                "severity": "HIGH",
                "risk_type": "MARKET_VOLATILITY_AMPLIFIER",
                "detail": f"VIX elevated at {vix.get('current')} - market volatility amplifies portfolio risk.",
            })

        return {
            "liquidity_status": liquidity_status,
            "equity_weight_pct": equity_pct,
            "anomalies": anomalies,
            "risk_flags": risk_flags,
            "anomaly_count": len(anomalies),
            "risk_flag_count": len(risk_flags),
        }


class AdvisoryAgent:
    """Translates analytical risk findings into prioritized advisory recommendations."""

    def run(self, profile: Dict[str, Any], analysis: Dict[str, Any], history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        logger.info("Advisory: formulating recommendations")
        recs = []

        # Urgent outreach for critical anomalies
        for anomaly in analysis.get("anomalies", []):
            if anomaly["severity"] == "CRITICAL":
                recs.append({
                    "priority": "URGENT",
                    "category": "Client Outreach",
                    "action": f"Contact {profile['name']} immediately to verify transaction {anomaly['tx_id']} (${anomaly['amount']:,.2f} on {anomaly['date']}) to rule out unauthorized wire transfer.",
                })

        # Liquidity deficit rebalancing
        if analysis.get("liquidity_status") == "DEFICIT":
            recs.append({
                "priority": "HIGH",
                "category": "Cash Rebalancing",
                "action": f"Restore cash buffer: reallocate fixed income yield or dividends to cover the ${profile.get('target_liquidity', 0):,.2f} target liquidity reserve.",
            })

        # Portfolio drift realignment
        if any(f["risk_type"] == "PORTFOLIO_DRIFT" for f in analysis.get("risk_flags", [])):
            recs.append({
                "priority": "MEDIUM",
                "category": "Portfolio Realignment",
                "action": f"Rebalance equity holdings down towards the {profile.get('risk_profile')} target allocation cap.",
            })

        # Rapid deployment review
        if any(f["risk_type"] == "RAPID_CAPITAL_DEPLOYMENT" for f in analysis.get("risk_flags", [])):
            recs.append({
                "priority": "MEDIUM",
                "category": "Investment Pacing",
                "action": "Review recent rapid investment pacing with client to confirm alignment with planned deployment schedule.",
            })

        # Volatility hedging
        if any(f["risk_type"] == "MARKET_VOLATILITY_AMPLIFIER" for f in analysis.get("risk_flags", [])):
            recs.append({
                "priority": "HIGH",
                "category": "Volatility Hedge",
                "action": "Consider defensive positioning or short-term treasury allocation given elevated market volatility (VIX).",
            })

        # Multi-session trend alert
        if history:
            prev = history[-1].get("anomaly_count", 0)
            curr = analysis.get("anomaly_count", 0)
            if curr > prev:
                recs.append({
                    "priority": "MEDIUM",
                    "category": "Trend Alert",
                    "action": f"Anomaly count rose from {prev} to {curr} compared to prior review. Conduct comprehensive account audit.",
                })

        if not recs:
            recs.append({
                "priority": "LOW",
                "category": "Portfolio Maintenance",
                "action": "Portfolio metrics within expected bounds. No immediate rebalancing required.",
            })

        return recs


# Orchestrator
class WealthAdvisorOrchestrator:
    def __init__(self, auto_approve: bool = False, memory_path: str = "wealth_advisor_memory.json"):
        self.auto_approve = auto_approve
        self.memory = Memory(storage_path=memory_path)

        self.tools = {
            "crm_api": CRMTool(),
            "portfolio_api": PortfolioTool(),
            "transaction_feed": TransactionFeedTool(),
            "market_data": MarketDataTool(),
        }

        self.fetcher = DataFetcherAgent(self.tools)
        self.analyzer = AnalyzerAgent()
        self.advisor = AdvisoryAgent()

    def _human_checkpoint(self, analysis: Dict[str, Any]) -> bool:
        if self.auto_approve:
            logger.info("HumanCheckpoint: auto-approved (--auto)")
            return True

        print(f"\n[Human Review Required]", file=sys.stderr)
        print(f"  Anomalies: {analysis['anomaly_count']} | Risk Flags: {analysis['risk_flag_count']} | Liquidity: {analysis['liquidity_status']}", file=sys.stderr)
        choice = input("Approve advisory recommendations? [y/N]: ").strip().lower()
        if choice in ("y", "yes"):
            logger.info("HumanCheckpoint: approved by operator")
            return True

        logger.warning("HumanCheckpoint: rejected by operator")
        return False

    def process_client_review(self, client_id: str) -> str:
        logger.info(f"Orchestrator: reviewing {client_id}")

        # 1. Ingest Data
        try:
            data = self.fetcher.run(client_id)
        except Exception as e:
            logger.error(f"Orchestrator: data fetch failed - {e}")
            return json.dumps({
                "status": "ABORTED",
                "client_id": client_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, indent=2)

        # 2. Analyze Risk
        analysis = self.analyzer.run(data)

        # 3. Checkpoint if anomalies or high-severity flags exist
        has_risks = analysis["anomaly_count"] > 0 or any(f["severity"] == "HIGH" for f in analysis["risk_flags"])
        if has_risks:
            if not self._human_checkpoint(analysis):
                return json.dumps({
                    "status": "ABORTED",
                    "client_id": client_id,
                    "reason": "Rejected at human review checkpoint",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, indent=2)

        # 4. Formulate Advisory
        history = self.memory.get_client_history(client_id)
        recs = self.advisor.run(data["profile"], analysis, history)

        # 5. Build Structured Dossier
        dossier = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "client_overview": {
                "client_id": data["profile"]["client_id"],
                "name": data["profile"]["name"],
                "location": data["profile"].get("location", "Jakarta, Indonesia"),
                "risk_tolerance": data["profile"]["risk_profile"],
                "investment_goals": data["profile"].get("investment_goals", ""),
                "total_aum_usd": data["portfolio"]["total_aum"],
                "tenure_years": data["profile"].get("tenure_years", 0),
            },
            "risk_assessment": {
                "anomalies": analysis["anomalies"],
                "risk_signals": analysis["risk_flags"],
                "liquidity_status": analysis["liquidity_status"],
                "equity_weight_pct": analysis["equity_weight_pct"],
            },
            "advisory_recommendations": recs,
            "execution_metadata": {
                "agents_invoked": ["DataFetcherAgent", "AnalyzerAgent", "AdvisoryAgent"],
                "status": "COMPLETED",
            },
        }

        # 6. Save history for cross-session trend tracking
        self.memory.save_history(client_id, {
            "timestamp": dossier["generated_at"],
            "anomaly_count": analysis["anomaly_count"],
            "risk_flag_count": analysis["risk_flag_count"],
            "liquidity_status": analysis["liquidity_status"],
            "recommendation_count": len(recs),
        })

        logger.info(f"Orchestrator: completed review for {client_id}")
        return json.dumps(dossier, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Wealth Advisor Assistant")
    parser.add_argument("client_id", nargs="?", default="CLIENT_1001", help="Client ID to process")
    parser.add_argument("--auto", action="store_true", help="Auto-approve checkpoints")
    parser.add_argument("--memory-file", default="wealth_advisor_memory.json", help="Memory file path")
    args = parser.parse_args()

    orchestrator = WealthAdvisorOrchestrator(auto_approve=args.auto, memory_path=args.memory_file)
    output = orchestrator.process_client_review(args.client_id)
    print(output)


if __name__ == "__main__":
    main()