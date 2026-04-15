"""
Research Agent — ObTrac + Google ADK

Capabilities:
  - Web search (simulated)
  - Calculator & unit converter
  - Multi-turn conversation via ADK sessions (session_id auto-tracked by ObTrac)

ObTrac integration:
  - before/after_agent_callback → root Trace per turn
  - @trace on tools → child Span per tool call
  - session_id auto-detected from ToolContext.invocation_context.session.id

Run with:
    adk web test_gadk/research_agent
    # then open http://localhost:8000
"""

import os
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from obtrac_sdk import obtrac_config
from test_gadk.tools.search_tool import web_search
from test_gadk.tools.calculator_tool import calculator, unit_converter
from test_gadk.callbacks import (
    obtrac_before_agent,
    obtrac_after_agent,
    obtrac_before_tool,
    obtrac_after_tool,
)

load_dotenv()

# ObTrac config — set once at module load
obtrac_config(
    project="adk-research-agent",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=False,
)

# LLM via LiteLLM — works with Azure OpenAI, OpenAI, Gemini, etc.
_model = LiteLlm(
    model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')}",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
)

root_agent = Agent(
    name="research_agent",
    model=_model,
    description="A research assistant that can search the web and do math.",
    instruction="""You are a helpful research assistant.

You have access to:
- web_search: to find information on any topic
- calculator: to evaluate math expressions (e.g. "15% of 4500", "sqrt(144)")
- unit_converter: to convert between units (km↔miles, kg↔lbs, celsius↔fahrenheit, usd↔inr)

Always use a tool when the user asks for calculations or factual information.
Give concise, accurate answers. Cite what you found when using web_search.""",
    tools=[web_search, calculator, unit_converter],
    before_agent_callback=obtrac_before_agent,
    after_agent_callback=obtrac_after_agent,
    before_tool_callback=obtrac_before_tool,
    after_tool_callback=obtrac_after_tool,
)
