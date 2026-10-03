"""Calculate illustrative net outcomes from explicit, single-cheque assumptions."""

from __future__ import annotations

import math


def number(value: object, name: str, minimum: float = 0.0, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise ValueError(f"{name} is outside its permitted range")
    return result


def probability(value: object) -> float:
    """Accept fractional probabilities; percent strings support historical payloads."""
    if isinstance(value, str) and value.strip().endswith("%"):
        return number(value.strip()[:-1], "probability", maximum=100) / 100
    return number(value, "probability", maximum=1)


def validate_scenarios(scenarios: list[dict[str, object]], *, modern: bool = False) -> None:
    if not scenarios:
        return  # A genuinely unavailable model is allowed, and blocks INVEST.
    if len(scenarios) < (4 if modern else 3):
        raise ValueError("return_scenarios must include at least 4 scenarios" if modern else
                         "return_scenarios must include at least 3 scenarios")
    probs = [probability(row.get("probability")) for row in scenarios]
    if not math.isclose(sum(probs), 1.0, abs_tol=1e-6):
        raise ValueError("Scenario probabilities must sum to 100%")
    if modern:
        if sorted(str(row.get("kind", "")) for row in scenarios) != ["base", "bear", "loss", "upside"]:
            raise ValueError("Include exactly one loss, bear, base and upside scenario")
        values = [number(row.get("exit_value"), "exit_value") for row in scenarios]
        if not any(v == 0 and p > 0 for v, p in zip(values, probs)):
            raise ValueError("Include an explicit total-loss scenario with positive probability")
        if next(v for row, v in zip(scenarios, values) if row["kind"] == "loss") != 0:
            raise ValueError("The loss scenario must have zero recovery")
    else:
        for row in scenarios:
            if "multiple" in row:
                number(str(row["multiple"]).lower().removesuffix("x"), "multiple")


def calculate_returns(
    assumptions: dict[str, object], scenarios: list[dict[str, object]],
    total_outlay: float, currency: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Use post-money illustrative ownership; no later capital is assumed.

    Exit values represent equity proceeds available to the modeled holding. Debt,
    preference stacks and conversion mechanics must already be reflected in them.
    Currency conversion uses valuation-currency units per investment-currency unit.
    """
    if not assumptions or not scenarios:
        return scenarios, {"status": "unavailable", "reason": "Explicit ownership, fees and exit assumptions were not supplied."}
    try:
        validate_scenarios(scenarios, modern=True)
        ticket = number(total_outlay, "total_outlay", minimum=0.01)
        entry = number(assumptions.get("entry_valuation"), "entry_valuation", minimum=0.01)
        if assumptions.get("entry_valuation_basis") != "post_money":
            raise ValueError("entry_valuation must be explicitly post-money")
        if assumptions.get("exit_value_basis") != "distributable_equity":
            raise ValueError("exit_value_basis must be distributable_equity")
        if assumptions.get("currency") != currency:
            raise ValueError("Return-model currency must match the investment currency")
        valuation_currency = str(assumptions.get("valuation_currency", ""))
        if not valuation_currency:
            raise ValueError("valuation_currency is required")
        fx = number(assumptions.get("fx_rate", 1 if valuation_currency == currency else None), "fx_rate", minimum=0.000001)
        if valuation_currency == currency and not math.isclose(fx, 1):
            raise ValueError("Same-currency fx_rate must equal 1")
        fee = number(assumptions.get("fee_rate"), "fee_rate", maximum=0.9999)
        dilution = number(assumptions.get("dilution_rate"), "dilution_rate", maximum=1)
        carry = number(assumptions.get("carry_rate"), "carry_rate", maximum=1)
        years = number(assumptions.get("years", 8), "years", minimum=1)
        if assumptions.get("follow_on") is not False:
            raise ValueError("Default return case must explicitly assume no follow-ons")
        fee_treatment = assumptions.get("fee_treatment")
        if fee_treatment not in {"deducted", "added"}:
            raise ValueError("fee_treatment must be deducted or added")
        carry_basis = assumptions.get("carry_basis")
        if carry_basis not in {"deployed_capital", "total_outlay"}:
            raise ValueError("carry_basis must be deployed_capital or total_outlay")
        deployed = ticket * (1 - fee) if fee_treatment == "deducted" else ticket / (1 + fee)
        ownership = deployed * fx / entry
        if ownership > 1:
            raise ValueError("Modeled entry ownership cannot exceed 100%")

        def outcomes(valuation: float) -> list[dict[str, object]]:
            result = []
            for row in scenarios:
                scenario_dilution = number(row.get("dilution_rate", dilution), "scenario dilution", maximum=1)
                holding_years = number(row.get("years", years), "scenario years", minimum=1)
                exit_ownership = deployed * fx / valuation * (1 - scenario_dilution)
                gross = number(row["exit_value"], "exit_value") * exit_ownership / fx
                capital_basis = deployed if carry_basis == "deployed_capital" else ticket
                net = gross - max(0, gross - capital_basis) * carry
                multiple = net / ticket
                result.append({
                    **row, "probability": probability(row["probability"]),
                    "ownership_at_exit": exit_ownership, "gross_proceeds": gross,
                    "net_proceeds": net, "net_multiple": multiple,
                    "annualized_return": multiple ** (1 / holding_years) - 1,
                    "years": holding_years, "dilution_rate": scenario_dilution,
                })
            return result

        calculated = outcomes(entry)
        expected = sum(float(r["net_proceeds"]) * float(r["probability"]) for r in calculated)
        best = max(calculated, key=lambda r: float(r["net_proceeds"]))
        stressed = outcomes(entry * 1.2)
        return calculated, {
            "status": "available", "total_outlay": ticket, "deployed_capital": deployed,
            "entry_ownership": ownership, "future_dilution": dilution, "years": years,
            "expected_net_proceeds": expected, "expected_net_multiple": expected / ticket,
            "total_loss_probability": sum(float(r["probability"]) for r in calculated if float(r["net_proceeds"]) == 0),
            "capital_loss_probability": sum(float(r["probability"]) for r in calculated if float(r["net_proceeds"]) < ticket),
            "upside_share_of_expected_proceeds": float(best["net_proceeds"]) * float(best["probability"]) / expected if expected else 0,
            "valuation_sensitivity": {
                "entry_valuation": entry * 1.2,
                "expected_net_multiple": sum(float(r["net_proceeds"]) * float(r["probability"]) for r in stressed) / ticket,
            },
        }
    except ValueError as exc:
        return scenarios, {"status": "unavailable", "reason": str(exc)}
