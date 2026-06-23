from datetime import date, time, datetime

import plotly.colors as pc
import plotly.graph_objects as go
import pandas as pd


def _minute_to_datetime(minute_val: int, day_base_minute: dict, workdays: list) -> datetime:
    """Convert a contiguous timeline minute to real-world datetime."""
    sorted_days = sorted(day_base_minute.items(), key=lambda x: x[1])  # (date, start_min)

    target_date = None
    minute_within_day = None
    day_start_time: time | None = None

    for i, (d, start_min) in enumerate(sorted_days):
        if i + 1 < len(sorted_days):
            next_start = sorted_days[i + 1][1]
        else:
            next_start = start_min + 8 * 60  # assume all days are 8h

        if minute_val < next_start:
            target_date = d
            minute_within_day = minute_val - start_min
            # Find the actual start_time from workdays
            for wd in workdays:
                if wd.date.date() == d:
                    day_start_time = wd.start_time
                    break
            break

    if target_date is None and sorted_days:
        # Fallback: assign to last day
        d, start_min = sorted_days[-1]
        target_date = d
        minute_within_day = minute_val - start_min

    if target_date is None:
        return datetime(2026, 1, 1)

    if day_start_time is None:
        day_start_time = time(8, 0)

    total_start_minutes = day_start_time.hour * 60 + day_start_time.minute
    actual_minutes = total_start_minutes + minute_within_day
    hour = actual_minutes // 60
    minute = actual_minutes % 60
    return datetime.combine(target_date, time(hour, minute))


def build_gantt(result: dict, day_base_minute: dict, workdays: list) -> go.Figure:
    """Build a Plotly Gantt chart from scheduling results."""
    assignments = result.get("assignments", [])
    if not assignments:
        return go.Figure()

    # Assign colors by order_id
    order_ids = sorted({a["order_id"] for a in assignments})
    colors = pc.qualitative.Set2
    color_map = {oid: colors[i % len(colors)] for i, oid in enumerate(order_ids)}

    fig = go.Figure()

    machine_ids = sorted({a["machine_id"] for a in assignments})
    y_labels = {m: i for i, m in enumerate(machine_ids)}

    for a in assignments:
        start_dt = _minute_to_datetime(a["start_minute"], day_base_minute, workdays)
        end_dt = _minute_to_datetime(a["end_minute"], day_base_minute, workdays)
        m = a["machine_id"]
        y_val = y_labels.get(m, 0)
        label_text = f"{a['order_id']}<br>{a['operation_id']} {a['operation_name']}<br>{a['duration_minute']}min"

        fig.add_trace(go.Bar(
            base=[start_dt],
            x=[(end_dt - start_dt).total_seconds() / 3600],  # hours for time deltas
            y=[y_val],
            orientation="h",
            name=a["order_id"],
            text=label_text,
            textposition="inside",
            textfont=dict(size=9, color="white"),
            marker=dict(color=color_map.get(a["order_id"], "#999"), line=dict(color="#333", width=0.5)),
            hovertemplate=(
                f"<b>{a['order_id']}</b><br>"
                f"{a['operation_id']} {a['operation_name']}<br>"
                f"设备: {a['machine_id']}<br>"
                f"开始: {start_dt.strftime('%m/%d %H:%M')}<br>"
                f"结束: {end_dt.strftime('%m/%d %H:%M')}<br>"
                f"耗时: {a['duration_minute']} min<br>"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.update_yaxes(
        tickvals=list(y_labels.values()),
        ticktext=[f"{m}" for m in machine_ids],
        title="设备",
        autorange="reversed",
    )
    fig.update_xaxes(title="时间", type="date")
    fig.update_layout(
        title="生产排程甘特图",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        barmode="stack",
        bargap=0.2,
    )

    return fig


def build_machine_utilization(result: dict) -> go.Figure:
    """Build a bar chart showing machine utilization."""
    assignments = result.get("assignments", [])
    if not assignments:
        return go.Figure()

    machine_load: dict[str, float] = {}
    makespan = result.get("makespan_minutes", 1)
    for a in assignments:
        m = a["machine_id"]
        machine_load[m] = machine_load.get(m, 0) + a.get("duration_minute", 0)

    machines = sorted(machine_load.keys())
    utils = [machine_load[m] / max(makespan, 1) * 100 for m in machines]

    fig = go.Figure(data=[
        go.Bar(
            x=machines,
            y=utils,
            text=[f"{u:.1f}%" for u in utils],
            textposition="outside",
            marker=dict(color="#2E75B6"),
        )
    ])
    fig.update_layout(
        title="设备利用率",
        yaxis=dict(title="利用率 (%)", range=[0, max(utils) * 1.3]),
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def build_delivery_summary(result: dict, orders: list, day_base_minute: dict, workdays: list) -> go.Figure:
    """Build a delivery performance summary chart."""
    assignments = result.get("assignments", [])
    if not assignments:
        return go.Figure()

    due_map = {}
    for o in orders:
        steps = [a for a in assignments if a["order_id"] == o.order_id]
        if steps:
            last_end = max(s["end_minute"] for s in steps)
            due_dt = _minute_to_datetime(last_end, day_base_minute, workdays)
            due_map[o.order_id] = {
                "due_date": o.due_date,
                "actual_end": due_dt,
                "lateness_hours": max(0, (due_dt - datetime.combine(o.due_date, time(17, 0))).total_seconds() / 3600),
            }

    orders_sorted = sorted(due_map.keys())
    lateness_vals = [due_map[o]["lateness_hours"] for o in orders_sorted]

    fig = go.Figure(data=[
        go.Bar(
            x=orders_sorted,
            y=lateness_vals,
            text=[f"{v:.1f}h" if v > 0 else "准时" for v in lateness_vals],
            textposition="outside",
            marker=dict(
                color=["#C0392B" if v > 0 else "#27AE60" for v in lateness_vals],
            ),
        )
    ])
    fig.update_layout(
        title="交期达成情况（延迟时间）",
        yaxis=dict(title="延迟 (小时)"),
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def build_summary_stats(result: dict, orders: list,
                        day_base_minute: dict, workdays: list) -> dict:
    """Return summary statistics as a dict."""
    assignments = result.get("assignments", [])
    if not assignments:
        return {}

    makespan = result.get("makespan_minutes", 0)
    total_op_minutes = sum(a["duration_minute"] for a in assignments)
    num_machines = len({a["machine_id"] for a in assignments})
    avg_load = total_op_minutes / max(num_machines * makespan, 1) * 100

    due_map = {}
    for o in orders:
        steps = [a for a in assignments if a["order_id"] == o.order_id]
        if steps:
            last_end = max(s["end_minute"] for s in steps)
            due_dt = _minute_to_datetime(last_end, day_base_minute, workdays)
            due_map[o.order_id] = {
                "due_date": o.due_date,
                "actual_end": due_dt,
                "late": due_dt > datetime.combine(o.due_date, time(17, 0)),
            }

    on_time = sum(1 for v in due_map.values() if not v["late"])
    late = sum(1 for v in due_map.values() if v["late"])

    return {
        "makespan_hours": round(makespan / 60, 1),
        "total_ops": len(assignments),
        "num_machines": num_machines,
        "avg_load_pct": round(avg_load, 1),
        "on_time_count": on_time,
        "late_count": late,
        "on_time_rate": round(on_time / max(on_time + late, 1) * 100, 1),
    }
