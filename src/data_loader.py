from datetime import datetime, time
from pathlib import Path

import pandas as pd

from .models import CalendarDay, Machine, RoutingStep, SchedulingInput, WorkOrder


def _get_sheet_names(filepath: str | Path) -> list[str]:
    """Return actual sheet names from the Excel file."""
    import openpyxl
    wb = openpyxl.load_workbook(filepath, read_only=True)
    names = wb.sheetnames
    wb.close()
    return names


def _read_sheet(filepath: str | Path, sheet_index: int, skip_leading_col: int = 1) -> pd.DataFrame:
    """Read a sheet by index: header at row 1 (0-indexed), drop first NaN column."""
    df = pd.read_excel(filepath, sheet_name=sheet_index, header=1)
    # Drop leading unnamed column (Excel row index)
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed")]
    if len(unnamed) == skip_leading_col:
        df = df.drop(columns=unnamed[:skip_leading_col])
    df = df.dropna(how="all").dropna(how="all", axis=1)
    return df


def read_orders(filepath: str | Path) -> list[WorkOrder]:
    df = _read_sheet(filepath, 0)
    orders: list[WorkOrder] = []
    for _, row in df.iterrows():
        orders.append(WorkOrder(
            order_id=str(row.iloc[0]).strip(),
            product_code=str(row.iloc[1]).strip(),
            product_name=str(row.iloc[2]).strip(),
            quantity=int(row.iloc[3]),
            due_date=pd.Timestamp(row.iloc[4]).to_pydatetime(),
            priority=int(row.iloc[5]),
            is_urgent=str(row.iloc[6]).strip() == "是",
        ))
    return orders


def read_routing(filepath: str | Path) -> list[RoutingStep]:
    df = _read_sheet(filepath, 1)
    steps: list[RoutingStep] = []
    for _, row in df.iterrows():
        machines_str = str(row.iloc[5]).strip()
        steps.append(RoutingStep(
            product_code=str(row.iloc[0]).strip(),
            operation_id=str(row.iloc[1]).strip(),
            operation_name=str(row.iloc[2]).strip(),
            sequence=int(row.iloc[3]),
            setup_time_min=float(row.iloc[4]),
            machines=[m.strip() for m in machines_str.split(",") if m.strip()],
            run_time_min=float(row.iloc[6]),
        ))
    return steps


def read_machines(filepath: str | Path) -> list[Machine]:
    df = _read_sheet(filepath, 2)
    machines: list[Machine] = []
    for _, row in df.iterrows():
        machines.append(Machine(
            machine_id=str(row.iloc[0]).strip(),
            machine_name=str(row.iloc[1]).strip(),
            shift_name=str(row.iloc[2]).strip(),
            daily_hours=float(row.iloc[3]),
            daily_minutes=float(row.iloc[4]),
            efficiency=float(row.iloc[5]),
            status=str(row.iloc[6]).strip(),
        ))
    return machines


def read_calendar(filepath: str | Path) -> list[CalendarDay]:
    df = _read_sheet(filepath, 3)
    days: list[CalendarDay] = []
    for _, row in df.iterrows():
        date_str = str(row.iloc[0]).strip()
        try:
            date_val = pd.Timestamp(date_str).to_pydatetime()
        except Exception:
            # Strange values like "2026-02-29" — skip
            continue
        is_workday = str(row.iloc[1]).strip() != "否"
        start_val = row.iloc[3]
        end_val = row.iloc[4]
        if isinstance(start_val, str):
            start_val = datetime.strptime(start_val.strip(), "%H:%M:%S").time()
        elif isinstance(start_val, time):
            pass
        else:
            start_val = pd.Timestamp(start_val).time()
        if isinstance(end_val, str):
            end_val = datetime.strptime(end_val.strip(), "%H:%M:%S").time()
        elif isinstance(end_val, time):
            pass
        else:
            end_val = pd.Timestamp(end_val).time()
        days.append(CalendarDay(
            date=date_val,
            is_workday=is_workday,
            shift_name=str(row.iloc[2]).strip(),
            start_time=start_val,
            end_time=end_val,
        ))
    return days


def load_scheduling_input(filepath: str | Path) -> SchedulingInput:
    """Load and validate all scheduling data from Excel."""
    orders = read_orders(filepath)
    routing = read_routing(filepath)
    machines = read_machines(filepath)
    calendar = read_calendar(filepath)

    inp = SchedulingInput(
        work_orders=orders,
        routing=routing,
        machines=machines,
        calendar=calendar,
    )

    issues = inp.validate_consistency()
    if issues:
        raise ValueError("数据一致性校验失败:\n" + "\n".join(f"  - {i}" for i in issues))

    return inp
