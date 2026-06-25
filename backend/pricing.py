from backend.models import EstimateRequest, LineItem


BASE_COSTS = {
    "wood_privacy": 38,
    "vinyl_privacy": 55,
    "chain_link": 24,
    "aluminum": 48,
    "split_rail": 22,
}

MATERIAL_GRADE_ADJUSTMENTS = {
    "economy": -4,
    "standard": 0,
    "premium": 6,
}

WALK_GATE_COST = 350
DOUBLE_GATE_COST = 650

GATE_HARDWARE_COSTS = {
    "standard": 0,
    "self_closing": 65,
    "lockable": 85,
}

REMOVAL_COST_PER_FOOT = 6
STAIN_SEAL_COST_PER_FOOT = 4
PERMIT_ADMIN_COST = 150

BRUSH_CLEARING_COSTS = {
    "none": 0,
    "light": 125,
    "moderate": 300,
    "heavy": 600,
}

SLOPE_MULTIPLIERS = {
    "none": 0.00,
    "slight": 0.05,
    "moderate": 0.10,
    "steep": 0.18,
}

ACCESS_MULTIPLIERS = {
    "easy": 0.00,
    "limited": 0.05,
    "difficult": 0.10,
}

HEIGHT_ADJUSTMENT_PER_EXTRA_FOOT = 4


def safe_getattr(obj, attr_name, default):
    value = getattr(obj, attr_name, default)

    if value is None:
        return default

    return value


def add_line_item(
    line_items: list[LineItem],
    label: str,
    quantity: float,
    unit: str,
    unit_cost: float,
):
    total = round(quantity * unit_cost, 2)

    if total == 0:
        return

    line_items.append(
        LineItem(
            label=label,
            quantity=round(float(quantity), 2),
            unit=unit,
            unit_cost=round(float(unit_cost), 2),
            total=total,
        )
    )


def add_fixed_line_item(
    line_items: list[LineItem],
    label: str,
    total: float,
):
    if total == 0:
        return

    line_items.append(
        LineItem(
            label=label,
            quantity=1,
            unit="fixed",
            unit_cost=round(float(total), 2),
            total=round(float(total), 2),
        )
    )


def resolve_slope_severity(req: EstimateRequest) -> str:
    slope_severity = safe_getattr(req, "slope_severity", "none")

    if slope_severity == "none" and req.slope_present:
        return "moderate"

    return slope_severity


def resolve_access_level(req: EstimateRequest) -> str:
    access_level = safe_getattr(req, "access_level", "easy")

    if access_level == "easy" and req.difficult_access:
        return "difficult"

    return access_level


def calculate_price(req: EstimateRequest):
    line_items: list[LineItem] = []

    material_grade = safe_getattr(req, "material_grade", "standard")
    gate_hardware = safe_getattr(req, "gate_hardware", "standard")
    brush_clearing = safe_getattr(req, "brush_clearing", "none")
    stain_seal = safe_getattr(req, "stain_seal", False)
    permit_admin = safe_getattr(req, "permit_admin", False)

    slope_severity = resolve_slope_severity(req)
    access_level = resolve_access_level(req)

    base_rate = BASE_COSTS[req.fence_type]
    base_label = f"{req.fence_type.replace('_', ' ').title()} fence installation"

    add_line_item(
        line_items=line_items,
        label=base_label,
        quantity=req.linear_feet,
        unit="linear feet",
        unit_cost=base_rate,
    )

    material_adjustment = MATERIAL_GRADE_ADJUSTMENTS.get(material_grade, 0)

    if material_adjustment != 0:
        material_label = (
            "Premium material upgrade"
            if material_adjustment > 0
            else "Economy material credit"
        )

        add_line_item(
            line_items=line_items,
            label=material_label,
            quantity=req.linear_feet,
            unit="linear feet",
            unit_cost=material_adjustment,
        )

    if req.height_ft > 6:
        extra_height_feet = req.height_ft - 6
        height_adjustment_rate = extra_height_feet * HEIGHT_ADJUSTMENT_PER_EXTRA_FOOT

        add_line_item(
            line_items=line_items,
            label=f"Height adjustment above 6 ft ({req.height_ft} ft)",
            quantity=req.linear_feet,
            unit="linear feet",
            unit_cost=height_adjustment_rate,
        )

    if req.gate_count > 0:
        add_line_item(
            line_items=line_items,
            label="Walk gate",
            quantity=req.gate_count,
            unit="each",
            unit_cost=WALK_GATE_COST,
        )

    if req.double_gate_count > 0:
        add_line_item(
            line_items=line_items,
            label="Double gate",
            quantity=req.double_gate_count,
            unit="each",
            unit_cost=DOUBLE_GATE_COST,
        )

    total_gate_units = req.gate_count + req.double_gate_count
    hardware_cost = GATE_HARDWARE_COSTS.get(gate_hardware, 0)

    if total_gate_units > 0 and hardware_cost > 0:
        hardware_label = {
            "self_closing": "Self-closing gate hardware",
            "lockable": "Lockable gate hardware",
        }.get(gate_hardware, "Gate hardware upgrade")

        add_line_item(
            line_items=line_items,
            label=hardware_label,
            quantity=total_gate_units,
            unit="gate",
            unit_cost=hardware_cost,
        )

    if req.old_fence_removal:
        removal_length = safe_getattr(req, "removal_length_feet", None)

        if not removal_length or removal_length <= 0:
            removal_length = req.linear_feet

        add_line_item(
            line_items=line_items,
            label="Old fence removal",
            quantity=removal_length,
            unit="linear feet",
            unit_cost=REMOVAL_COST_PER_FOOT,
        )

    brush_cost = BRUSH_CLEARING_COSTS.get(brush_clearing, 0)

    if brush_cost > 0:
        brush_label = {
            "light": "Light brush clearing",
            "moderate": "Moderate brush clearing",
            "heavy": "Heavy brush clearing",
        }.get(brush_clearing, "Brush clearing")

        add_fixed_line_item(
            line_items=line_items,
            label=brush_label,
            total=brush_cost,
        )

    if stain_seal:
        add_line_item(
            line_items=line_items,
            label="Stain or seal option",
            quantity=req.linear_feet,
            unit="linear feet",
            unit_cost=STAIN_SEAL_COST_PER_FOOT,
        )

    if permit_admin:
        add_fixed_line_item(
            line_items=line_items,
            label="Permit or HOA admin support",
            total=PERMIT_ADMIN_COST,
        )

    subtotal = round(sum(item.total for item in line_items), 2)

    adjustment_items: list[LineItem] = []

    slope_multiplier = SLOPE_MULTIPLIERS.get(slope_severity, 0)

    if slope_multiplier > 0:
        slope_adjustment_total = round(subtotal * slope_multiplier, 2)

        adjustment_items.append(
            LineItem(
                label=f"{slope_severity.title()} slope adjustment",
                quantity=round(slope_multiplier * 100, 2),
                unit="% of subtotal",
                unit_cost=subtotal,
                total=slope_adjustment_total,
            )
        )

    access_multiplier = ACCESS_MULTIPLIERS.get(access_level, 0)

    if access_multiplier > 0:
        access_base = subtotal + sum(item.total for item in adjustment_items)
        access_adjustment_total = round(access_base * access_multiplier, 2)

        adjustment_items.append(
            LineItem(
                label=f"{access_level.title()} access adjustment",
                quantity=round(access_multiplier * 100, 2),
                unit="% of subtotal",
                unit_cost=access_base,
                total=access_adjustment_total,
            )
        )

    line_items.extend(adjustment_items)

    estimated_total = round(sum(item.total for item in line_items), 2)

    low_range = round(estimated_total * 0.90, 2)
    high_range = round(estimated_total * 1.15, 2)

    return line_items, subtotal, estimated_total, low_range, high_range