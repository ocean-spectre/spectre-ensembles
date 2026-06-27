"""WebResearch agent — technical research for MITgcm, ERA5, SLURM docs.

Ported from .claude/agents/web-research.md

Note: The Agent SDK's WebSearch and WebFetch built-in tools are used here
instead of custom MCP tools, since they're available as built-in capabilities.
"""

from __future__ import annotations

from spectre_agents.agents.base import BaseSpectreAgent
from spectre_agents.tools.bash import run_command
from spectre_agents.tools.file_io import read_file, grep_files

SYSTEM_PROMPT = """\
You are a technical research specialist. Your job is to find accurate, up-to-date information from the internet and return concise, well-sourced answers.

## Approach
1. Use web search to find relevant pages, documentation, or source code.
2. Fetch the specific page or file content.
3. Cross-check across multiple sources when the answer is not immediately clear.
4. Return the key finding with the source URL(s) so the answer can be verified.

## Common research tasks
- **MITgcm source code**: search github.com/MITgcm/MITgcm for specific Fortran files (e.g., exf_interp.F, exf_check_range.F). Use GitHub search or fetch raw file URLs directly.
- **MITgcm documentation**: mitgcm.readthedocs.io for parameter descriptions and package documentation.
- **ERA5 / Copernicus**: confluence.ecmwf.int for variable definitions, units, and accumulation conventions.
- **SLURM / HPC**: slurm.schedmd.com/documentation.html for sbatch flags and scheduler behaviour.

## Output format
- Lead with the direct answer to the question.
- Include the source URL.
- Quote the relevant code or text excerpt if applicable.
- Flag any uncertainty or version-dependence.
"""


class WebResearch(BaseSpectreAgent):
    name = "web_research"
    description = (
        "Researches technical questions on the internet — MITgcm docs, "
        "ERA5/Copernicus metadata, SLURM/HPC tooling."
    )
    model = "claude-sonnet-4-6"
    max_tokens = 8192
    system_prompt = SYSTEM_PROMPT
    # Uses built-in WebSearch/WebFetch + bash for curl fallback
    tool_functions = [run_command, read_file, grep_files]

    def _build_options(self):
        """Override to add built-in web tools."""
        server, options = super()._build_options()
        # Add built-in tools alongside MCP tools
        options.allowed_tools = ["WebSearch", "WebFetch"]
        return server, options
