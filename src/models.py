from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class WorkOrder(BaseModel):
    """工单：一张生产任务单"""
    order_id: str
    product_code: str
    product_name: str
    quantity: int = Field(gt=0)
    due_date: datetime
    priority: int = Field(default=1, ge=1, le=10)
    is_urgent: bool = False

    @field_validator("order_id")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("工单号不能为空")
        return v.strip()


class RoutingStep(BaseModel):
    """工序：产品工艺路线中的一道工序"""
    product_code: str
    operation_id: str
    operation_name: str
    sequence: int = Field(ge=1)
    setup_time_min: float = Field(default=0, ge=0)
    machines: list[str]
    run_time_min: float = Field(gt=0)

    @field_validator("machines")
    @classmethod
    def not_empty_list(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("适用设备不能为空")
        return [m.strip() for m in v if m.strip()]


class Machine(BaseModel):
    """设备：一台可用于排程的生产设备"""
    machine_id: str
    machine_name: str
    shift_name: str = "白班"
    daily_hours: float = Field(gt=0)
    daily_minutes: float = Field(gt=0)
    efficiency: float = Field(default=1.0, ge=0, le=1.0)
    status: str = "正常"

    @field_validator("machine_id")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("设备ID不能为空")
        return v.strip()


class CalendarDay(BaseModel):
    """工作日历中的一天"""
    date: datetime
    is_workday: bool = True
    shift_name: str = "白班"
    start_time: time
    end_time: time


class SchedulingInput(BaseModel):
    """排程问题的完整输入"""
    work_orders: list[WorkOrder]
    routing: list[RoutingStep]
    machines: list[Machine]
    calendar: list[CalendarDay]

    def validate_consistency(self) -> list[str]:
        """Check cross-table data integrity. Returns list of issues (empty = valid)."""
        issues: list[str] = []

        product_codes_in_orders = {o.product_code for o in self.work_orders}
        product_codes_in_routing = {r.product_code for r in self.routing}
        machine_ids = {m.machine_id for m in self.machines}

        # Every ordered product must have a routing
        for pc in product_codes_in_orders - product_codes_in_routing:
            issues.append(f"产品 {pc} 有工单但缺少工艺路线数据")

        # Every routing's machines must exist
        for r in self.routing:
            for m in r.machines:
                if m not in machine_ids:
                    issues.append(f"工艺 {r.product_code}/{r.operation_id} 引用了不存在的设备 {m}")

        return issues
