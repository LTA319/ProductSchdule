from src.data_loader import load_scheduling_input


def test_load_real_data():
    """Verify the real sample data loads without errors."""
    inp = load_scheduling_input("docs/机加工生产排程示例数据.xlsx")

    assert len(inp.work_orders) == 5
    assert len(inp.routing) == 12
    assert len(inp.machines) == 5
    assert len(inp.calendar) > 0

    # Check consistency
    issues = inp.validate_consistency()
    assert not issues, f"Unexpected consistency issues: {issues}"

    # Verify specific data points
    assert inp.work_orders[0].order_id == "SO20260226-001"
    assert inp.work_orders[0].quantity == 50
    assert inp.machines[2].efficiency == 0.95

    # Every order must have routing steps
    product_codes = {o.product_code for o in inp.work_orders}
    for pc in product_codes:
        steps = [s for s in inp.routing if s.product_code == pc]
        assert steps, f"Product {pc} has no routing steps"
        assert len({s.sequence for s in steps}) == len(steps), f"Duplicate sequence for {pc}"


def test_work_order_validation():
    """Test Pydantic validation catches bad data."""
    from src.models import WorkOrder

    # Valid
    wo = WorkOrder(
        order_id="WO-001", product_code="PART-A", product_name="Test",
        quantity=10, due_date="2026-03-15", priority=1
    )
    assert wo.order_id == "WO-001"

    # Invalid: zero quantity
    import pytest
    with pytest.raises(Exception):
        WorkOrder(
            order_id="WO-002", product_code="PART-A", product_name="Test",
            quantity=0, due_date="2026-03-15", priority=1
        )


def test_machine_validation():
    """Test Machine model validation."""
    from src.models import Machine

    m = Machine(
        machine_id="M01", machine_name="CNC Lathe",
        daily_hours=8, daily_minutes=480, efficiency=1.0
    )
    assert m.machine_id == "M01"
