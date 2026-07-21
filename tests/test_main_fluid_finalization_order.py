from __future__ import annotations

import ast
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def _main_function() -> ast.FunctionDef:
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )


def _calls_named(function: ast.FunctionDef, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == name
            or isinstance(node.func, ast.Name)
            and node.func.id == name
        )
    ]


def test_controller_evidence_is_snapshotted_before_fluid_finalization():
    function = _main_function()
    evidence_call, = _calls_named(function, "online_fluid_control_evidence")
    finalize_call, = _calls_named(function, "finalize_episode")

    assert evidence_call.lineno < finalize_call.lineno
    keywords = {keyword.arg: keyword.value for keyword in finalize_call.keywords}
    assert isinstance(keywords["controller_evidence"], ast.Name)
    assert keywords["controller_evidence"].id == "control_evidence"
    assert isinstance(keywords["terminal_phase"], ast.Name)
    assert keywords["terminal_phase"].id == "terminal_phase"
    assert isinstance(keywords["terminal_action"], ast.Name)
    assert keywords["terminal_action"].id == "action"


def test_main_records_limit_boundary_separately_from_limit_termination():
    function = _main_function()
    keys = {
        key.value
        for node in ast.walk(function)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }

    assert "observation_limit_boundary" in keys
    assert "observation_limit_termination" in keys


def test_controlled_contact_action_uses_fail_closed_transaction_helper():
    function = _main_function()
    transaction_call, = _calls_named(
        function, "execute_controlled_action_transaction"
    )
    keywords = {keyword.arg: keyword.value for keyword in transaction_call.keywords}

    assert isinstance(keywords["read_action_context"], ast.Lambda)
    assert isinstance(keywords["apply_action"], ast.Lambda)
    assert _calls_named(function, "validate_controlled_action_proposal") == []
    assert _calls_named(function, "commit_controlled_action") == []
    assert _calls_named(function, "confirm_controlled_action_applied") == []


def test_controlled_monitor_start_is_not_treated_as_mechanical_attachment():
    function = _main_function()
    direct_boolean_uses = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and any(
            isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Attribute)
            and candidate.func.attr == "maybe_attach"
            for candidate in ast.walk(node.test)
        )
    ]
    mechanical_checks = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute)
        and node.attr == "mechanical_attachment_used"
    ]

    assert direct_boolean_uses == []
    assert mechanical_checks


def test_controlled_terminal_transition_is_handled_before_state_access():
    function = _main_function()
    terminal_branches = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and any(
            isinstance(candidate, ast.Constant)
            and candidate.value == "CONTROLLED_TERMINAL_TRANSITION"
            for candidate in ast.walk(node.test)
        )
    ]
    assert len(terminal_branches) == 1
    terminal_branch = terminal_branches[0]
    state_assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "state"
            for target in node.targets
        )
        and any(
            isinstance(candidate, ast.Name)
            and candidate.id == "fluid_observation"
            for candidate in ast.walk(node.value)
        )
    ]
    branch_calls = {
        candidate.func.attr
        for candidate in ast.walk(terminal_branch)
        if isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Attribute)
    }

    assert state_assignments
    assert terminal_branch.lineno < min(node.lineno for node in state_assignments)
    assert "abort_online_fluid_episode" in branch_calls
    assert "seal_attempt" in branch_calls


def test_pending_controlled_terminal_preempts_reset_and_unknown_apply_closes_world():
    function = _main_function()
    attributes = [
        node.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute)
    ]
    strings = [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]

    assert "controlled_terminal_pending" in attributes
    assert "controlled_interval_pending" in attributes
    assert "requires_world_termination" in strings
    assert _calls_named(function, "validate_controlled_terminal_transition")


def test_controlled_observe_failure_closes_runtime():
    function = _main_function()
    guarded_observe = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Try)
        and _calls_named(node, "observe")
        and _calls_named(node, "_close_controlled_runtime")
    ]

    assert len(guarded_observe) == 1


def test_controlled_monitor_validation_precedes_controller_proposal():
    function = _main_function()
    maybe_attach_calls = _calls_named(function, "maybe_attach")
    controller_steps = [
        node
        for node in _calls_named(function, "step")
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "task_controller"
    ]

    assert len(maybe_attach_calls) == 2
    assert len(controller_steps) == 1
    assert min(call.lineno for call in maybe_attach_calls) < controller_steps[0].lineno


def test_controlled_normal_completion_resets_or_closes_without_playing_timeline():
    function = _main_function()
    completion_branches = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and any(
            isinstance(candidate, ast.Name)
            and candidate.id == "controlled_contact_mode"
            for candidate in ast.walk(node.test)
        )
        and any(
            isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Name)
            and candidate.func.id == "reset_task_then_controller"
            for candidate in ast.walk(node)
        )
    ]
    task_complete_calls = _calls_named(function, "on_task_complete")

    assert len(completion_branches) == 1
    assert task_complete_calls
    assert any(
        completion_branches[0].lineno > call.lineno
        for call in task_complete_calls
    )


def test_controlled_terminal_action_is_rejected_before_direct_apply():
    function = _main_function()
    errors = [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    apply_calls = _calls_named(function, "apply_action")
    terminal_error_nodes = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Constant)
        and node.value == "controlled_contact_terminal_action_forbidden"
    ]

    assert "controlled_contact_terminal_action_forbidden" in errors
    assert len(terminal_error_nodes) == 1
    assert apply_calls
    assert terminal_error_nodes[0].lineno < min(
        call.lineno for call in apply_calls
    )
