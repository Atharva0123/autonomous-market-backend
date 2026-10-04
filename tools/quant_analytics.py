"""Portfolio analytics adapter."""
from tools.base import GenericJSONTool


def portfolio_optimizer(settings):
    """Return the endpoint-configured portfolio optimizer tool."""
    return GenericJSONTool("Portfolio Optimizer", "Portfolio risk and allocation analytics.",
                           settings.portfolio_optimizer_base_url, settings=settings)
