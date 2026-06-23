from pathlib import Path

import streamlit as st
import pandas as pd

from src.data_loader import load_scheduling_input, read_orders, read_routing, read_machines, read_calendar
from src.scheduler import solve_schedule
from src.visualizer import (
    build_gantt,
    build_machine_utilization,
    build_delivery_summary,
    build_summary_stats,
)

st.set_page_config(page_title="生产排程智能体", layout="wide")

st.title("生产排程智能体")
st.caption("Python + OR-Tools + Streamlit | 机加工排程原型")

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("数据导入")
    uploaded_file = st.file_uploader(
        "上传Excel排程数据",
        type=["xlsx"],
        help="包含4个Sheet：工单表、工艺路线表、设备表、工作日历",
    )

    default_path = Path("docs/机加工生产排程示例数据.xlsx")
    use_default = st.checkbox("使用示例数据", value=not uploaded_file)

    st.header("排程参数")
    time_limit = st.slider("求解时间上限（秒）", 10, 600, 60, step=10)

    st.header("关于")
    st.markdown("""
    **生产排程智能体 v0.1**

    基于 OR-Tools CP-SAT 求解器，
    支持多设备替代、效率系数、
    工作日历约束。
    """)

# ── Load data ──────────────────────────────────────────────────────
data_path = None
if uploaded_file is not None:
    # Save uploaded file to temp
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.getbuffer())
        data_path = tmp.name
elif use_default and default_path.exists():
    data_path = str(default_path)

if data_path is None:
    st.warning("请上传Excel文件或使用示例数据")
    st.stop()

try:
    with st.spinner("正在加载数据..."):
        inp = load_scheduling_input(data_path)
    st.success(f"数据加载完成：{len(inp.work_orders)} 张工单 | {len(inp.routing)} 道工序 | {len(inp.machines)} 台设备 | {len(inp.calendar)} 天工作日历")
except Exception as e:
    st.error(f"数据加载失败: {e}")
    st.stop()

# ── Tabs ───────────────────────────────────────────────────────────
tab_data, tab_result = st.tabs(["数据预览", "排程结果"])

with tab_data:
    st.subheader("工单表")
    orders_df = pd.DataFrame([{
        "工单号": o.order_id,
        "产品编码": o.product_code,
        "产品名称": o.product_name,
        "数量": o.quantity,
        "交货日期": o.due_date.strftime("%Y-%m-%d"),
        "优先级": o.priority,
        "是否紧急": "是" if o.is_urgent else "否",
    } for o in inp.work_orders])
    st.dataframe(orders_df, use_container_width=True, hide_index=True)

    st.subheader("工艺路线表")
    routing_df = pd.DataFrame([{
        "产品编码": r.product_code,
        "工序号": r.operation_id,
        "工序名称": r.operation_name,
        "顺序": r.sequence,
        "标准工时(min)": r.setup_time_min,
        "适用设备": ", ".join(r.machines),
        "加工时间(min)": r.run_time_min,
    } for r in inp.routing])
    st.dataframe(routing_df, use_container_width=True, hide_index=True)

    st.subheader("设备表")
    machines_df = pd.DataFrame([{
        "设备编码": m.machine_id,
        "设备名称": m.machine_name,
        "班次": m.shift_name,
        "日工作小时": m.daily_hours,
        "日工作分钟": m.daily_minutes,
        "效率系数": m.efficiency,
        "状态": m.status,
    } for m in inp.machines])
    st.dataframe(machines_df, use_container_width=True, hide_index=True)

    st.subheader("工作日历")
    cal_df = pd.DataFrame([{
        "日期": d.date.strftime("%Y-%m-%d"),
        "是否工作日": "是" if d.is_workday else "否",
        "班次": d.shift_name,
        "开始": d.start_time.strftime("%H:%M"),
        "结束": d.end_time.strftime("%H:%M"),
    } for d in inp.calendar])
    st.dataframe(cal_df, use_container_width=True, hide_index=True)

with tab_result:
    if st.button("开始排程", type="primary", use_container_width=True):
        with st.spinner("正在求解排程模型..."):
            result, day_base_minute, workdays = solve_schedule(inp, time_limit_seconds=time_limit)

        if result["status"] in ("OPTIMAL", "FEASIBLE"):
            st.success(f"排程完成！状态: {result['status']} | 求解耗时: {result['wall_time_seconds']:.2f}s | 总完工时间: {result['makespan_minutes']} 分钟")

            # Summary cards
            stats = build_summary_stats(result, inp.work_orders, day_base_minute, workdays)
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("总完工时间", f"{stats.get('makespan_hours', 0)} h")
            col2.metric("工序总数", stats.get("total_ops", 0))
            col3.metric("设备数", stats.get("num_machines", 0))
            col4.metric("平均负荷", f"{stats.get('avg_load_pct', 0)}%")
            col5.metric("准时交付率", f"{stats.get('on_time_rate', 0)}%")

            col_left, col_right = st.columns([2, 1])
            with col_left:
                st.plotly_chart(build_gantt(result, day_base_minute, workdays), use_container_width=True)
            with col_right:
                st.plotly_chart(build_machine_utilization(result), use_container_width=True)

            st.plotly_chart(build_delivery_summary(result, inp.work_orders, day_base_minute, workdays), use_container_width=True)

            # Detail table
            st.subheader("排程明细")
            detail_df = pd.DataFrame([{
                "工单号": a["order_id"],
                "产品编码": a["product_code"],
                "工序号": a["operation_id"],
                "工序名称": a["operation_name"],
                "顺序": a["sequence"],
                "设备": a["machine_id"],
                "开始分钟": a["start_minute"],
                "结束分钟": a["end_minute"],
                "耗时(min)": a["duration_minute"],
            } for a in result["assignments"]])
            st.dataframe(detail_df, use_container_width=True, hide_index=True)

            # Export
            csv = detail_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("导出排程结果 (CSV)", csv, "schedule_result.csv", "text/csv")
        else:
            st.error(f"排程失败: {result['status']}。请检查数据是否存在冲突约束。")
