from ortools.sat.python import cp_model

from .models import SchedulingInput


def solve_schedule(inp: SchedulingInput, time_limit_seconds: float = 300.0):
    """
    Build and solve the production scheduling problem using OR-Tools CP-SAT.
    Uses optional intervals for alternative machines.
    """
    # ── 1. Data preparation ──────────────────────────────────────────

    orders = inp.work_orders
    routing = inp.routing
    machines = inp.machines

    machine_by_id = {m.machine_id: m for m in machines}
    machine_ids = sorted(machine_by_id.keys())

    workdays = sorted(
        [d for d in inp.calendar if d.is_workday],
        key=lambda d: d.date,
    )
    if not workdays:
        raise ValueError("工作日历中没有工作日")

    # Build contiguous timeline: each workday's minutes are concatenated
    day_base_minute: dict = {}
    minute_offset = 0
    for d in workdays:
        day_base_minute[d.date.date()] = minute_offset
        mins = (d.end_time.hour * 60 + d.end_time.minute) - (d.start_time.hour * 60 + d.start_time.minute)
        minute_offset += mins

    total_working_minutes = minute_offset
    horizon = total_working_minutes * 3  # generous buffer

    # Which date does a given minute fall into
    day_ranges = sorted(day_base_minute.items(), key=lambda x: x[1])  # (date, start_min)
    day_end_map = {}
    for i, (date, start) in enumerate(day_ranges):
        if i + 1 < len(day_ranges):
            day_end_map[date] = day_ranges[i + 1][1]
        else:
            day_end_map[date] = total_working_minutes

    # Product routing lookup
    product_steps: dict[str, list] = {}
    for r in routing:
        product_steps.setdefault(r.product_code, []).append(r)
    for pc in product_steps:
        product_steps[pc].sort(key=lambda s: s.sequence)

    # ── 2. Build operation list ──────────────────────────────────────
    class JobOp:
        __slots__ = ("order_id", "product_code", "operation_id", "operation_name",
                     "duration_min", "machines", "sequence", "due_date")

    all_ops: list[JobOp] = []
    for o in orders:
        steps = product_steps.get(o.product_code, [])
        for step in steps:
            op = JobOp()
            op.order_id = o.order_id
            op.product_code = o.product_code
            op.operation_id = step.operation_id
            op.operation_name = step.operation_name
            op.sequence = step.sequence
            op.duration_min = int(step.run_time_min)
            op.machines = list(step.machines)
            op.due_date = o.due_date.date()
            all_ops.append(op)

    # ── 3. CP-SAT model ──────────────────────────────────────────────
    model = cp_model.CpModel()

    # Each operation → set of optional intervals (one per eligible machine)
    op_alt_starts: dict = {}   # (order_id, op_id, machine_id) -> IntVar
    op_alt_ends: dict = {}     # (order_id, op_id, machine_id) -> IntVar
    op_alt_intervals: dict = {}  # (order_id, op_id, machine_id) -> OptionalIntervalVar
    op_alt_present: dict = {}    # (order_id, op_id, machine_id) -> BoolVar

    for op in all_ops:
        key = (op.order_id, op.operation_id)
        op_alt_starts[key] = {}
        op_alt_ends[key] = {}
        op_alt_intervals[key] = {}
        op_alt_present[key] = {}

        for m_id in op.machines:
            if m_id not in machine_by_id:
                continue
            eff = machine_by_id[m_id].efficiency
            dur = max(1, int(round(op.duration_min / eff))) if eff > 0 else op.duration_min

            s = model.NewIntVar(0, horizon, f"s_{op.order_id}_{op.operation_id}_{m_id}")
            e = model.NewIntVar(0, horizon, f"e_{op.order_id}_{op.operation_id}_{m_id}")
            pres = model.NewBoolVar(f"pres_{op.order_id}_{op.operation_id}_{m_id}")
            iv = model.NewOptionalIntervalVar(s, dur, e, pres,
                                              f"iv_{op.order_id}_{op.operation_id}_{m_id}")
            op_alt_starts[key][m_id] = s
            op_alt_ends[key][m_id] = e
            op_alt_intervals[key][m_id] = iv
            op_alt_present[key][m_id] = pres

        # Exactly one machine per operation
        model.AddExactlyOne(list(op_alt_present[key].values()))

    # Sequence constraints within each job: op_n.end <= op_{n+1}.start
    for o in orders:
        steps = product_steps.get(o.product_code, [])
        for i in range(len(steps) - 1):
            cur_key = (o.order_id, steps[i].operation_id)
            nxt_key = (o.order_id, steps[i + 1].operation_id)
            # Across all machine choices: for any machine pair (a, b),
            # if cur on a AND nxt on b → cur_end_a <= nxt_start_b
            for ma in steps[i].machines:
                if ma not in machine_by_id or ma not in op_alt_ends[cur_key]:
                    continue
                for mb in steps[i + 1].machines:
                    if mb not in machine_by_id or mb not in op_alt_starts[nxt_key]:
                        continue
                    # Implication: if pres_a AND pres_b → cur_end_a <= nxt_start_b
                    both = model.NewBoolVar(f"seq_{o.order_id}_{i}_{ma}_{mb}")
                    model.AddBoolAnd([op_alt_present[cur_key][ma], op_alt_present[nxt_key][mb]]).OnlyEnforceIf(both)
                    model.AddBoolOr([op_alt_present[cur_key][ma].Not(), op_alt_present[nxt_key][mb].Not(), both])
                    model.Add(op_alt_ends[cur_key][ma] <= op_alt_starts[nxt_key][mb]).OnlyEnforceIf(both)

    # Machine no-overlap
    for m_id in machine_ids:
        machine_ivs = []
        for op in all_ops:
            key = (op.order_id, op.operation_id)
            if m_id in op_alt_intervals[key]:
                machine_ivs.append(op_alt_intervals[key][m_id])
        if machine_ivs:
            model.AddNoOverlap(machine_ivs)

    # Makespan variable
    makespan_var = model.NewIntVar(0, horizon, "makespan")
    for op in all_ops:
        key = (op.order_id, op.operation_id)
        for m_id in op_alt_ends[key]:
            model.Add(makespan_var >= op_alt_ends[key][m_id])

    # Due date soft constraints
    lateness_vars = []
    for o in orders:
        steps = product_steps.get(o.product_code, [])
        if not steps:
            continue
        last_step = steps[-1]
        key = (o.order_id, last_step.operation_id)
        due_date_obj = o.due_date.date()
        if due_date_obj in day_end_map:
            due_minute = day_end_map[due_date_obj]
            lateness = model.NewIntVar(0, horizon, f"lateness_{o.order_id}")
            for m_id in op_alt_ends[key]:
                model.Add(lateness >= op_alt_ends[key][m_id] - due_minute)
            lateness_vars.append(lateness)

    # Objective: minimize makespan + weighted lateness
    obj_terms = [makespan_var]
    for lat in lateness_vars:
        obj_terms.append(lat * 100)
    model.Minimize(sum(obj_terms))

    # ── 4. Solve ─────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8

    print(f"Solving: {len(all_ops)} ops on {len(machine_ids)} machines, horizon={horizon}min")
    status = solver.Solve(model)

    status_name = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
    }.get(status, f"STATUS_{status}")

    result = {
        "status": status_name,
        "wall_time_seconds": solver.WallTime(),
        "makespan_minutes": None,
        "assignments": [],
    }

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result["makespan_minutes"] = solver.Value(makespan_var)
        for op in all_ops:
            key = (op.order_id, op.operation_id)
            chosen = None
            s_val = None
            e_val = None
            for m_id in op.machines:
                if m_id in op_alt_present[key] and solver.Value(op_alt_present[key][m_id]):
                    chosen = m_id
                    s_val = solver.Value(op_alt_starts[key][m_id])
                    e_val = solver.Value(op_alt_ends[key][m_id])
                    break
            result["assignments"].append({
                "order_id": op.order_id,
                "product_code": op.product_code,
                "operation_id": op.operation_id,
                "operation_name": op.operation_name,
                "sequence": op.sequence,
                "machine_id": chosen,
                "start_minute": s_val,
                "end_minute": e_val,
                "duration_minute": e_val - s_val if s_val is not None and e_val is not None else None,
            })
        result["assignments"].sort(key=lambda a: (a["start_minute"] or 0, a["machine_id"] or ""))
    else:
        print(f"Solver returned {status_name}")

    return result, day_base_minute, workdays
