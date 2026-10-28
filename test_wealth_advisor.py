"""Unit and integration tests for wealth advisor multi-agent system."""

import json
import tempfile
from pathlib import Path
import pytest
from wealth_advisor_agent import (
    CRMTool,
    PortfolioTool,
    TransactionFeedTool,
    MarketDataTool,
    Memory,
    DataFetcherAgent,
    AnalyzerAgent,
    AdvisoryAgent,
    WealthAdvisorOrchestrator,
    CRM_DATA,
)


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def tools():
    return {
        "crm_api": CRMTool(),
        "portfolio_api": PortfolioTool(),
        "transaction_feed": TransactionFeedTool(),
        "market_data": MarketDataTool(),
    }


# Tools
def test_crm_tool_lookup():
    tool = CRMTool()
    profile = tool.run("CLIENT_1001")
    assert profile["name"] == "Budi Santoso"
    assert profile["location"] == "Jakarta, Indonesia"
    assert profile["risk_profile"] == "Moderate"


def test_crm_tool_not_found():
    tool = CRMTool()
    with pytest.raises(KeyError):
        tool.run("NON_EXISTENT_CLIENT")


# Memory
def test_memory_persistence(tmp_path):
    mem_file = str(tmp_path / "mem.json")
    mem = Memory(storage_path=mem_file)
    mem.save_history("CLIENT_1001", {"anomaly_count": 2})

    mem_reload = Memory(storage_path=mem_file)
    history = mem_reload.get_client_history("CLIENT_1001")
    assert len(history) == 1
    assert history[0]["anomaly_count"] == 2


# Agents
def test_data_fetcher_agent(tools):
    agent = DataFetcherAgent(tools)
    data = agent.run("CLIENT_1001")
    assert "profile" in data
    assert "portfolio" in data
    assert "transactions" in data
    assert len(data["transactions"]) > 0


def test_analyzer_detects_liquidity_deficit():
    agent = AnalyzerAgent()
    mock_data = {
        "profile": {"risk_profile": "Moderate", "target_liquidity": 20000.0},
        "portfolio": {"cash_balance": 5000.0, "equities_value": 50000.0, "total_aum": 55000.0},
        "transactions": [],
        "market": {},
    }
    result = agent.run(mock_data)
    assert result["liquidity_status"] == "DEFICIT"
    assert any(flag["risk_type"] == "LIQUIDITY_DEFICIT" for flag in result["risk_flags"])


def test_analyzer_detects_outlier_and_large_withdrawal():
    agent = AnalyzerAgent()
    mock_data = {
        "profile": {"risk_profile": "Moderate", "target_liquidity": 10000.0},
        "portfolio": {"cash_balance": 15000.0, "equities_value": 50000.0, "total_aum": 65000.0},
        "transactions": [
            {"tx_id": "TX_1", "date": "2026-10-01", "type": "dividend", "amount": 500.0},
            {"tx_id": "TX_2", "date": "2026-10-05", "type": "fee", "amount": 100.0},
            {"tx_id": "TX_3", "date": "2026-10-15", "type": "withdrawal", "amount": 45000.0},
        ],
        "market": {},
    }
    result = agent.run(mock_data)
    assert result["anomaly_count"] >= 1
    outlier = [a for a in result["anomalies"] if a["tx_id"] == "TX_3"][0]
    assert outlier["severity"] == "CRITICAL"


def test_analyzer_detects_portfolio_drift():
    agent = AnalyzerAgent()
    mock_data = {
        "profile": {"risk_profile": "Moderate", "target_liquidity": 10000.0},  # Moderate cap is 50%
        "portfolio": {"cash_balance": 15000.0, "equities_value": 70000.0, "total_aum": 100000.0},  # 70% equities
        "transactions": [],
        "market": {},
    }
    result = agent.run(mock_data)
    assert any(flag["risk_type"] == "PORTFOLIO_DRIFT" for flag in result["risk_flags"])


def test_advisory_generates_recommendations():
    advisor = AdvisoryAgent()
    profile = CRM_DATA["CLIENT_1001"]
    analysis = {
        "liquidity_status": "DEFICIT",
        "anomalies": [{"tx_id": "TX_999", "amount": 35000.0, "severity": "CRITICAL", "date": "2026-10-18"}],
        "risk_flags": [{"risk_type": "PORTFOLIO_DRIFT"}],
        "anomaly_count": 1,
    }
    recs = advisor.run(profile, analysis, history=[])
    categories = [r["category"] for r in recs]
    assert "Client Outreach" in categories
    assert "Cash Rebalancing" in categories
    assert "Portfolio Realignment" in categories


def test_advisory_trend_detection_on_historical_increase():
    advisor = AdvisoryAgent()
    profile = CRM_DATA["CLIENT_1001"]
    analysis = {
        "liquidity_status": "ADEQUATE",
        "anomalies": [{"tx_id": "TX_1", "amount": 5000.0, "severity": "MEDIUM", "date": "2026-10-10"}],
        "risk_flags": [],
        "anomaly_count": 2,
    }
    history = [{"anomaly_count": 0}]
    recs = advisor.run(profile, analysis, history=history)
    assert any(r["category"] == "Trend Alert" for r in recs)


# Orchestrator & End-to-End
def test_orchestrator_end_to_end(tmp_path):
    mem_file = str(tmp_path / "test_mem.json")
    orch = WealthAdvisorOrchestrator(auto_approve=True, memory_path=mem_file)
    output = orch.process_client_review("CLIENT_1001")
    dossier = json.loads(output)

    assert "client_overview" in dossier
    assert "risk_assessment" in dossier
    assert "advisory_recommendations" in dossier
    assert dossier["client_overview"]["client_id"] == "CLIENT_1001"
    assert dossier["client_overview"]["name"] == "Budi Santoso"
    assert dossier["client_overview"]["location"] == "Jakarta, Indonesia"
    assert len(dossier["advisory_recommendations"]) > 0


def test_orchestrator_missing_client(tmp_path):
    mem_file = str(tmp_path / "test_mem.json")
    orch = WealthAdvisorOrchestrator(auto_approve=True, memory_path=mem_file)
    output = orch.process_client_review("NON_EXISTENT")
    result = json.loads(output)
    assert result["status"] == "ABORTED"


def test_human_checkpoint_interactive_rejection(tmp_path, monkeypatch):
    mem_file = str(tmp_path / "test_mem.json")
    orch = WealthAdvisorOrchestrator(auto_approve=False, memory_path=mem_file)
    monkeypatch.setattr("builtins.input", lambda _: "n")

    output = orch.process_client_review("CLIENT_1001")
    result = json.loads(output)
    assert result["status"] == "ABORTED"
    assert "Rejected" in result["reason"]
