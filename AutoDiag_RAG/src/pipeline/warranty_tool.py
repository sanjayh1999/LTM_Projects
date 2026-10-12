import json
from pathlib import Path

RULES_FILE = Path("data/warranty_rules.json")

with open(RULES_FILE, "r", encoding="utf-8") as f:
    WARRANTY_RULES = json.load(f)


def check_warranty(manufacturer: str, component: str, vehicle_age_years: float, mileage: int):
    """
    Deterministic warranty coverage check.

    Returns a dict:
        {
            "status": "covered" | "not_covered" | "needs_review",
            "reason": str,
            "rule_used": dict or None
        }
    """
    manufacturer = manufacturer.strip().title()
    component = component.strip().lower()

    mfr_rules = WARRANTY_RULES.get(manufacturer)
    if not mfr_rules:
        return {
            "status": "needs_review",
            "reason": f"No warranty rules found for manufacturer '{manufacturer}'.",
            "rule_used": None,
        }

    rule = mfr_rules.get(component)
    if not rule:
        return {
            "status": "needs_review",
            "reason": f"No specific rule found for component '{component}' under {manufacturer}. "
                      f"Available components: {list(mfr_rules.keys())}",
            "rule_used": None,
        }

    years_limit = rule.get("years")
    miles_limit = rule.get("miles")  # None means unlimited mileage

    age_ok = vehicle_age_years <= years_limit if years_limit is not None else True
    miles_ok = mileage <= miles_limit if miles_limit is not None else True

    if age_ok and miles_ok:
        status = "covered"
        reason = (
            f"{component.title()} is covered under {manufacturer}'s policy "
            f"({years_limit} years / {miles_limit if miles_limit else 'unlimited'} miles). "
            f"Vehicle is {vehicle_age_years} years old with {mileage} miles — within limits."
        )
    else:
        status = "not_covered"
        failed_on = []
        if not age_ok:
            failed_on.append(f"vehicle age ({vehicle_age_years} yrs) exceeds limit ({years_limit} yrs)")
        if not miles_ok:
            failed_on.append(f"mileage ({mileage}) exceeds limit ({miles_limit})")
        reason = (
            f"{component.title()} is NOT covered under {manufacturer}'s policy: "
            f"{', '.join(failed_on)}."
        )

    return {
        "status": status,
        "reason": reason,
        "rule_used": rule,
    }


if __name__ == "__main__":
    test_cases = [
        ("Honda", "powertrain", 4, 55000),      # should be covered
        ("Honda", "powertrain", 6, 55000),      # not covered - age exceeded
        ("Toyota", "corrosion", 4, 90000),      # covered - unlimited miles
        ("Hyundai", "basic", 3, 40000),         # covered
        ("Toyota", "hybrid_battery", 9, 140000),# covered
        ("Kia", "powertrain", 3, 30000),        # needs_review - no rules for Kia
    ]

    for mfr, comp, age, miles in test_cases:
        result = check_warranty(mfr, comp, age, miles)
        print(f"{mfr} | {comp} | {age}yrs, {miles}mi")
        print(f"  -> [{result['status'].upper()}] {result['reason']}")
        print()