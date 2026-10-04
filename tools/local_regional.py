"""Regional finance and validation tools."""
from __future__ import annotations
from typing import Any
from tools.base import ProviderTool, GenericJSONTool
from schemas.api_models import ToolRequest, ToolResult
import re


class MFAPITool(ProviderTool):
    name, description = "MFAPI", "Indian mutual fund scheme NAV history."
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs); self.endpoint = self.settings.mfapi_base_url.rstrip("/")
    def request_spec(self, request: ToolRequest) -> tuple[str, dict[str, Any], dict[str, str], Any]:
        scheme = str(request.params.get("scheme_code", request.symbol or ""))
        if scheme.isdigit():
            return f"{self.endpoint}/{scheme}", {}, {}, None
        return f"{self.endpoint}/search", {"q": request.query}, {}, None

    async def run(self, request: ToolRequest) -> ToolResult:
        """Resolve a scheme by name, then fetch its history; accept explicit numeric codes directly."""
        explicit = str(request.params.get("scheme_code", request.symbol or ""))
        if explicit.isdigit():
            return await super().run(request)
        search = await super().run(request)
        if not search.ok or not isinstance(search.data, list) or not search.data:
            return search
        match = search.data[0]
        if not isinstance(match, dict):
            return search
        code = match.get("schemeCode") or match.get("scheme_code")
        if not code:
            return search
        history = await super().run(ToolRequest(query=request.query, params={"scheme_code": str(code)}))
        if history.ok:
            history.data = {"scheme": match, "nav_history": history.data,
                            "scheme_search": search.data}
        return history


class RazorpayIFSCTool(ProviderTool):
    """Razorpay's public IFSC record lookup."""
    name, description = "Razorpay IFSC", "Indian bank branch detail lookup by IFSC."

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.endpoint = self.settings.razorpay_ifsc_base_url.rstrip("/")

    def request_spec(self, request: ToolRequest):
        code = str(request.params.get("ifsc") or "")
        if not code:
            match = re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", request.query.upper())
            code = match.group(0) if match else ""
        return f"{self.endpoint}/{code}" if code else "", {}, {}, None

    async def run(self, request: ToolRequest) -> ToolResult:
        url, _, _, _ = self.request_spec(request)
        if not url:
            return ToolResult(provider=self.name, ok=False, error="Provide an 11-character IFSC code to look up a branch.")
        return await super().run(request)


def regional_tools(settings: Any) -> list[ProviderTool]:
    return [GenericJSONTool("Bank Data", "IBAN and SWIFT validation.", settings.bank_data_base_url, settings=settings),
            RazorpayIFSCTool(settings=settings),
            GenericJSONTool("Tax Data", "VAT and tax registration validation.", settings.tax_data_base_url, settings=settings)]
