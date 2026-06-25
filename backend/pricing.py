from backend.models import EstimateRequest, LineItem


BASE_COSTS = {
    "wood_privacy": 38,
    "vinyl_privacy": 55,
    "chain_link": 24,
    "aluminum": 48,
    "split_rail": 22,
}

WALK_GATE_COST = 350
DOUBLE_GATE_COST = 650
REMOVAL_COST_PER_FOOT = 6


def calculate_price(req: EstimateRequest):
    line_items = []

    base_rate = BASE_COSTS[req.fence_type]
    base_total = req.linear_feet * base_rate

    line_items.append(
        LineItem(
            label=f"{req.fence_type.replace('_', ' ').title()} fence",
            quantity=req.linear_feet,
            unit="linear feet",
            unit_cost=base_rate,
            total=round(base_total, 2),
        )
    )

    if req.gate_count > 0:
        line_items.append(
            LineItem(
                label="Walk gate",
                quantity=req.gate_count,
                unit="each",
                unit_cost=WALK_GATE_COST,
                total=round(req.gate_count * WALK_GATE_COST, 2),
            )
        )

    if req.double_gate_count > 0:
        line_items.append(
            LineItem(
                label="Double gate",
                quantity=req.double_gate_count,
                unit="each",
                unit_cost=DOUBLE_GATE_COST,
                total=round(req.double_gate_count * DOUBLE_GATE_COST, 2),
            )
        )

    if req.old_fence_removal:
        line_items.append(
            LineItem(
                label="Old fence removal",
                quantity=req.linear_feet,
                unit="linear feet",
                unit_cost=REMOVAL_COST_PER_FOOT,
                total=round(req.linear_feet * REMOVAL_COST_PER_FOOT, 2),
            )
        )

    subtotal = round(sum(item.total for item in line_items), 2)

    complexity_multiplier = 1.0

    if req.slope_present:
        complexity_multiplier += 0.10

    if req.difficult_access:
        complexity_multiplier += 0.08

    estimated_total = round(subtotal * complexity_multiplier, 2)
    low_range = round(estimated_total * 0.90, 2)
    high_range = round(estimated_total * 1.15, 2)

    return line_items, subtotal, estimated_total, low_range, high_range