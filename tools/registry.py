"""Central registry for exactly twenty provider tools."""
import asyncio
from config import Settings, get_settings
from tools.base import ProviderTool
from tools.market_equity import MarketstackTool, OpenFIGITool, AletheiaTool, generic_equity_tools
from tools.sentiment_news import sentiment_tools
from tools.macro_geopolitics import DrillrTool, macro_tools
from tools.local_regional import MFAPITool, regional_tools
from tools.quant_analytics import portfolio_optimizer


def build_tool_registry(settings: Settings | None = None) -> dict[str, ProviderTool]:
    """Create all 20 tools with shared configuration and unique names."""
    s = settings or get_settings()
    tools = [MarketstackTool(settings=s), OpenFIGITool(settings=s), AletheiaTool(settings=s), DrillrTool(settings=s), MFAPITool(settings=s),
             *generic_equity_tools(s), *sentiment_tools(s), *macro_tools(s),
             *regional_tools(s), portfolio_optimizer(s)]
    registry = {tool.name: tool for tool in tools}
    shared_limit = asyncio.Semaphore(s.max_concurrent_requests)
    for tool in registry.values():
        tool.semaphore = shared_limit
    if len(registry) != 20:
        raise RuntimeError(f"Expected 20 registered tools, found {len(registry)}")
    return registry
