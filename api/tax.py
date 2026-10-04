"""Narrow, citation-backed India listed-investment tax estimate."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException

from api.models import IndiaTaxEstimate, IndiaTaxEstimateRequest, SourceCitation

TAX_PAGE = "https://www.incometaxindia.gov.in/en/sale-of-shares"
TAX_GUIDE = ("https://wmstatic-prd.incometaxindia.gov.in/documents/20117/42998/"
             "Income-from-capital-gains_2025-12-09_01-26-34_a14c08_en.pdf/"
             "042d19de-3306-dcf1-b2c1-22ad1a55ca50?download=true")


def estimate_india_gain(request: IndiaTaxEstimateRequest) -> IndiaTaxEstimate:
    """Estimate the special-rate capital-gains component for supported sales only.

    The supported FY2025-26 rules cover resident-individual, listed equity and
    equity-oriented mutual funds. Securities transaction tax eligibility is
    required. Business income, non-residents, loss set-off, surcharge, cess,
    rebates, other income, and filing positions are out of scope.
    """
    if request.transfer_date < request.acquisition_date:
        raise HTTPException(status_code=422, detail="Transfer date must be on or after acquisition date.")
    if request.transfer_date > date(2026, 3, 31):
        raise HTTPException(status_code=422, detail="Only transfers through FY2025-26 are currently rule-validated.")
    if not request.stt_eligible:
        raise HTTPException(status_code=422, detail="This estimate supports only STT-eligible listed investments; other cases are unsupported.")
    if request.transfer_date < date(2024, 7, 23):
        raise HTTPException(status_code=422, detail="Pre-23 July 2024 transfers are not supported by this first estimator.")

    gross_gain = request.sale_value_inr - request.purchase_value_inr - request.eligible_costs_inr
    months_held = ((request.transfer_date.year - request.acquisition_date.year) * 12
                   + request.transfer_date.month - request.acquisition_date.month
                   - (request.transfer_date.day < request.acquisition_date.day))
    is_long_term = months_held >= 12
    if is_long_term:
        remaining_annual_exemption = max(0.0, 125_000 - request.prior_112a_gains_inr)
        taxable_gain = max(0.0, gross_gain - remaining_annual_exemption)
        rate = 12.5
        tax = taxable_gain * rate / 100
        gain_type = "long_term"
    else:
        taxable_gain = max(0.0, gross_gain)
        rate = 20.0
        tax = taxable_gain * rate / 100
        gain_type = "short_term"

    return IndiaTaxEstimate(
        tax_year=request.tax_year, gain_type=gain_type, gross_gain_inr=round(gross_gain, 2),
        taxable_gain_inr=round(taxable_gain, 2), applicable_rate_pct=rate,
        estimated_tax_before_surcharge_cess_inr=round(tax, 2),
        assumptions=[
            "Resident individual; eligible listed equity/equity-oriented fund disposal with Securities Transaction Tax paid.",
            "Transfers are after 23 July 2024 and within FY2025-26; listed equity/equity-fund long-term threshold is 12 months.",
            "For section 112A, the INR 125,000 annual threshold is applied using the user-provided prior eligible gains.",
            "Estimate excludes surcharge, cess, loss set-off/carry-forward, rebates, other income, treaty effects, and filing adjustments; it is not a tax return or advice.",
        ],
        citations=[
            SourceCitation(source_id="india-capital-gains-rules", name="Income Tax Department of India",
                url=TAX_PAGE, dataset="Capital gains guidance / sections 111A and 112A",
                record_id="FY2025-26; transfer-date rules", retrieved_at=datetime.now(timezone.utc),
                observed_at="FY2025-26", cadence="law and official guidance may change",
                status="available", usage_note="Verify applicability and current official guidance before filing."),
            SourceCitation(source_id="india-capital-gains-guide", name="Income Tax Department of India",
                url=TAX_GUIDE, dataset="Income from Capital Gains guidance", record_id="FY2025-26",
                retrieved_at=datetime.now(timezone.utc), observed_at="FY2025-26",
                cadence="law and official guidance may change", status="available"),
        ],
    )
