# ui/components/gate_plan.py

import streamlit as st


def render_map_gate_plan(gate_points, manual_walk_gates, manual_double_gates):
    """
    Lets the user turn map marker points into structured gate counts.

    In the MVP, markers do not need to snap to the fence line. They are treated
    as estimator context and converted into walk-gate/double-gate counts for
    pricing and review.
    """

    gate_plan = []
    walk_gate_count_from_map = 0
    double_gate_count_from_map = 0

    st.subheader("Map-Based Gate Placement")
    st.caption(
        "Optional: use the marker tool on the map to place gate locations. "
        "Each marker can be classified as a walk gate or double gate."
    )

    if not gate_points:
        st.info("No gate markers detected. Manual gate counts will be used.")
        return {
            "gate_plan": gate_plan,
            "final_gate_count": int(manual_walk_gates),
            "final_double_gate_count": int(manual_double_gates),
            "use_map_gates": False,
            "gate_plan_notes": "",
        }

    st.success(f"Detected {len(gate_points)} gate marker(s) from the map.")

    use_map_gates = st.checkbox(
        "Use map gate markers for gate counts",
        value=True,
        help=(
            "When selected, FenceScope uses the gate markers below instead of "
            "the manual gate count fields above."
        ),
    )

    with st.container(border=True):
        for idx, gate in enumerate(gate_points):
            st.markdown(f"**Gate {idx + 1}**")

            gate_col1, gate_col2, gate_col3 = st.columns([1.2, 1, 1.4])

            with gate_col1:
                gate_type = st.selectbox(
                    f"Gate {idx + 1} type",
                    ["walk_gate", "double_gate"],
                    format_func=lambda value: {
                        "walk_gate": "Walk gate",
                        "double_gate": "Double gate",
                    }[value],
                    key=f"map_gate_type_{idx}",
                )

            with gate_col2:
                gate_width = st.number_input(
                    f"Gate {idx + 1} width",
                    min_value=3.0,
                    max_value=16.0,
                    value=4.0 if gate_type == "walk_gate" else 10.0,
                    step=1.0,
                    key=f"map_gate_width_{idx}",
                )

            with gate_col3:
                st.caption(
                    f"Location: {gate['lat']:.6f}, {gate['lng']:.6f}"
                )

            gate_plan.append(
                {
                    "gate_number": idx + 1,
                    "gate_type": gate_type,
                    "width_ft": float(gate_width),
                    "lat": gate["lat"],
                    "lng": gate["lng"],
                }
            )

            if gate_type == "walk_gate":
                walk_gate_count_from_map += 1
            else:
                double_gate_count_from_map += 1

            if idx < len(gate_points) - 1:
                st.divider()

    if use_map_gates:
        final_gate_count = walk_gate_count_from_map
        final_double_gate_count = double_gate_count_from_map
        st.write(
            f"**Gate counts used for estimate:** {final_gate_count} walk gate(s), "
            f"{final_double_gate_count} double gate(s)."
        )
    else:
        final_gate_count = int(manual_walk_gates)
        final_double_gate_count = int(manual_double_gates)
        st.write(
            f"**Gate counts used for estimate:** {final_gate_count} manual walk gate(s), "
            f"{final_double_gate_count} manual double gate(s)."
        )

    gate_plan_notes = ""

    if gate_plan:
        gate_plan_notes = "\n\nMap gate placement:\n" + "\n".join(
            [
                (
                    f"- Gate {gate['gate_number']}: "
                    f"{gate['gate_type'].replace('_', ' ')} "
                    f"({gate['width_ft']:.0f} ft), "
                    f"marker at {gate['lat']:.6f}, {gate['lng']:.6f}"
                )
                for gate in gate_plan
            ]
        )

    return {
        "gate_plan": gate_plan,
        "final_gate_count": final_gate_count,
        "final_double_gate_count": final_double_gate_count,
        "use_map_gates": use_map_gates,
        "gate_plan_notes": gate_plan_notes,
    }