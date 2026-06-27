"""SPECTRE agent definitions.

Each agent class wraps a Claude Agent SDK session with a specialized system prompt
and tool set, mirroring the .claude/agents/*.md definitions.
"""

from spectre_agents.agents.workflow_runner import WorkflowRunner
from spectre_agents.agents.stdout_diagnostics import StdoutDiagnostics
from spectre_agents.agents.model_output_review import ModelOutputReview
from spectre_agents.agents.namelist_validator import NamelistValidator
from spectre_agents.agents.forcing_data_qc import ForcingDataQC
from spectre_agents.agents.dashboard_manager import DashboardManager
from spectre_agents.agents.notify import DiscordNotifier
from spectre_agents.agents.web_research import WebResearch

AGENT_REGISTRY: dict[str, type] = {
    "workflow-runner": WorkflowRunner,
    "mitgcm-stdout-diagnostics": StdoutDiagnostics,
    "model-output-review": ModelOutputReview,
    "namelist-validator": NamelistValidator,
    "forcing-data-qc": ForcingDataQC,
    "dashboard-manager": DashboardManager,
    "notify": DiscordNotifier,
    "web-research": WebResearch,
}

__all__ = [
    "AGENT_REGISTRY",
    "WorkflowRunner",
    "StdoutDiagnostics",
    "ModelOutputReview",
    "NamelistValidator",
    "ForcingDataQC",
    "DashboardManager",
    "DiscordNotifier",
    "WebResearch",
]
