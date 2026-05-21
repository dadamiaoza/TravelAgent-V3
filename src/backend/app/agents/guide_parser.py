"""Guide Parser Agent - Step 3 + S11 MCP integration.

Parses unstructured travelogue text into structured Source Entities.
S11: integrated Tavily (search) + Firecrawl (scrape) via MCP.
Agent decides when to search, scrape, geocode, and parse.
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from app.agents.tools.geo import geocode_poi
from app.core.config import settings
from app.mcp.client import MCPClientWrapper

# MCP clients (lazy singleton, shared across agent instances)

_tavily = MCPClientWrapper("tavily", {
    "command": "npx",
    "args": ["-y", "tavily-mcp"],
    "transport": "stdio",
    "env": {"TAVILY_API_KEY": settings.tavily_api_key},
})

_firecrawl = MCPClientWrapper("firecrawl", {
    "command": "npx",
    "args": ["-y", "firecrawl-mcp"],
    "transport": "stdio",
    "env": {"FIRECRAWL_API_KEY": settings.firecrawl_api_key},
})


def create_guide_parser():
    """Create a guide-parsing agent with MCP search + scrape tools."""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    tools = [geocode_poi, *_tavily.get_tools(), *_firecrawl.get_tools()]

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=(
            "You are a travel guide acquisition and parsing assistant.\n\n"
            "## Core Principle\n"
            "Determine the type of user input and choose the appropriate workflow:\n"
            "1. User provides **guide TEXT directly** -> go straight to PARSING (do NOT search)\n"
            "2. User **asks to SEARCH** for guides (e.g. 'search for Hangzhou 3-day guide') -> SEARCH -> CONFIRM -> SCRAPE -> PARSE\n\n"
            "## Parsing Workflow (when you have guide text)\n"
            "1. Extract all POIs (attractions) mentioned in the text\n"
            "2. For each POI, also extract suggested_duration_h, best_time, cost_estimate when the text provides evidence (see field rules below)\n"
            "3. Infer which day each POI belongs to (day_index starting from 1); number them by appearance order within each day (seq)\n"
            "4. Call geocode_poi for each POI to get coordinates\n"
            "5. After collecting all results, output as a JSON array\n\n"
            "## Search Workflow (only when user explicitly asks to search)\n"
            "1. Use Tavily search tool to search for Chinese travel guides\n"
            "2. Present the returned URL list to the user for confirmation - do NOT let user select blindly\n"
            "3. After user confirms, use Firecrawl scrape tool to fetch each URL as Markdown\n"
            "4. Once you have the text, switch to Parsing Workflow\n\n"
            "Output JSON format (no other text):\n"
            '[{"poi_name": "...", "day_index": 1, "seq": 1, "lat": 0.0, "lng": 0.0,\n'
            '  "suggested_duration_h": null, "best_time": null, "cost_estimate": null}, ...]\n\n'
            "## Field Rules\n"
            "### suggested_duration_h (float | null)\n"
            "- MUST be a float, never a string like \"3-4\" or \"约2小时\"\n"
            '- "建议游玩3-4小时" -> 3.5 (midpoint of range)\n'
            '- "约2小时" -> 2.0\n'
            '- "半天" -> 4.0\n'
            '- "一整天" -> 8.0\n'
            "- No mention of duration -> null\n\n"
            "### best_time (\"morning\" | \"afternoon\" | \"evening\" | \"all_day\" | null)\n"
            "- Use ONLY these exact string values, nothing else\n"
            "- Fill ONLY when the text has explicit wording or strong semantic signal:\n"
            '  - \"一定要早上去\" / \"清晨最美\" -> \"morning\"\n'
            '  - \"下午去光线好\" / \"适合午后逛\" -> \"afternoon\"\n'
            '  - \"看日落\" / \"夜景\" / \"傍晚\" -> \"evening\"\n'
            '  - \"全天开放\" / \"可以玩一天\" -> \"all_day\"\n'
            "- Do NOT guess. \"适合拍照\", \"夏天建议避开中午\", vague descriptions -> null\n"
            "- When uncertain, output null\n\n"
            "### cost_estimate (string | null)\n"
            "- Output ONLY when the text contains an explicit ticket price or fee amount\n"
            '- \"门票60元\" -> \"门票60元\"\n'
            '- \"免费开放\" -> \"免费\"\n'
            '- \"缆车往返80元\" -> \"缆车往返80元\"\n'
            "- Do NOT extract from vague descriptions:\n"
            '  - \"便宜\" / \"略贵\" / \"性价比高\" -> null (no numeric value)\n'
            '  - \"几十块钱\" -> null (not specific)\n'
            '- No explicit price mentioned -> null\n\n'
            "Rules:\n"
            "- If the text does not explicitly separate days, all POIs belong to day_index=1\n"
            "- If the same POI appears multiple times, keep only the first occurrence\n"
            "- Use the coordinates returned by geocode_poi\n"
            "- When user pastes text directly, do NOT search - parse directly\n"
            "- All three new fields default to null; only fill when evidence exists in the text"
        ),
    )
