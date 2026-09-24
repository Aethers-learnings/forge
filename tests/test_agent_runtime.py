from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_runtime.runtime import Classification, ForgeRuntime, Task, dependency_satisfied, model_routing, next_safe_task, parse_reviewer_result, parse_tasks


TASKS = """\
- [x] T-001 — Done. Depends on: none. Classification: SAFE_INCREMENTAL.
- [ ] T-002 — Safe next. Depends on: T-001. Classification: SAFE_INCREMENTAL.
- [ ] T-003 — Wait. Depends on: T-999. Classification: SAFE_INCREMENTAL.
- [ ] T-004 — Review me. Depends on: T-001. Classification: MAJOR_REVIEW.
- [ ] T-005 — Approve me. Depends on: none. Classification: HUMAN_APPROVAL_REQUIRED.
"""


def test_tasks_parser_extracts_state_dependencies_and_classification():
    tasks = parse_tasks(TASKS)
    assert tasks[0].complete is True
    assert tasks[1].dependencies == ("T-001",)
    assert tasks[3].classification is Classification.MAJOR_REVIEW


def test_dependency_resolution_and_safe_selection():
    tasks = parse_tasks(TASKS)
    assert dependency_satisfied(tasks[1], tasks)
    assert not dependency_satisfied(tasks[2], tasks)
    assert next_safe_task(tasks).id == "T-002"


def test_governance_blocks_before_modification(tmp_path: Path):
    runtime = ForgeRuntime(tmp_path)
    with pytest.raises(PermissionError): runtime.safety_gate(Task("T-1", False, "x", (), Classification.MAJOR_REVIEW))
    with pytest.raises(PermissionError): runtime.safety_gate(Task("T-2", False, "x", (), Classification.HUMAN_APPROVAL_REQUIRED))


def test_dirty_paths_and_touched_paths_preserve_prior_work(tmp_path: Path):
    def runner(command, **kwargs):
        if command[:3] == ("git", "status", "--porcelain=v1"):
            return subprocess.CompletedProcess(command, 0, " M forge_backend.py\0?? agent_runtime/new.py\0", "")
        return subprocess.CompletedProcess(command, 0, "", "")
    runtime = ForgeRuntime(tmp_path, runner=runner)
    assert runtime.dirty_paths() == {"forge_backend.py", "agent_runtime/new.py"}
    assert runtime.task_touched_paths({"forge_backend.py"}) == {"agent_runtime/new.py"}


def test_reviewer_json_is_strict():
    assert parse_reviewer_result('{"result":"PASS","findings":[]}')["result"] == "PASS"
    for bad in ("PASS", '{"result":"PASS"}', '{"result":"PASS","findings":[],"extra":true}', '{"result":"MAYBE","findings":[]}'):
        with pytest.raises(ValueError): parse_reviewer_result(bad)


def test_check_selection_is_deterministic(tmp_path: Path):
    checks = ForgeRuntime(tmp_path).select_checks({"agent_runtime/runtime.py", "tests/test_agent_runtime.py", "static/forge_demo.html", "mobile/src/app/index.tsx"})
    assert checks[0] == ("git", "diff", "--check")
    assert ("node", "tests/csrf_frontend.cjs") in checks
    assert ("npm", "test", "--prefix", "mobile") in checks
    assert any(command[1:3] == ("-m", "pytest") for command in checks)


def test_model_routes_defaults_and_overrides():
    routes = model_routing({"FORGE_AUTO_MODEL_REPAIR": "custom"})
    assert routes["planner"] == "gpt-5.6-luna"
    assert routes["implementer"] == "gpt-5.6-terra"
    assert routes["security_reviewer"] == "gpt-5.6-sol"
    assert routes["repair"] == "custom"


def test_docs_and_sensitive_tasks_get_deterministic_special_routing(tmp_path: Path):
    runtime = ForgeRuntime(tmp_path)
    assert runtime._implementation_role(Task("T-1", False, "Add documentation", (), Classification.SAFE_INCREMENTAL)) == "docs_implementer"
    assert runtime._reviewer_role(Task("T-2", False, "Harden upload authorization", (), Classification.SAFE_INCREMENTAL)) == "security_reviewer"


def test_security_reviewer_uses_the_strict_reviewer_contract(tmp_path: Path):
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    artifact = tmp_path / "artifact"; artifact.mkdir()
    prompts = tmp_path / "agent_runtime/prompts"; prompts.mkdir(parents=True)
    (prompts / "reviewer.txt").write_text("Return exactly JSON")
    sandbox = tmp_path / "sandbox"; sandbox.mkdir()
    (sandbox / "run-locked.sh").write_text("#!/usr/bin/env bash\n")
    ForgeRuntime(tmp_path, runner=runner).invoke("security_reviewer", "packet", artifact)
    assert "Return exactly JSON" in commands[0][-1]


def test_model_call_budget_and_repair_limit(tmp_path: Path):
    runtime = ForgeRuntime(tmp_path, env={"FORGE_AUTO_MAX_CALLS": "1", "FORGE_AUTO_MAX_REPAIRS": "2"})
    runtime.calls = 1
    artifact = tmp_path / "artifact"; artifact.mkdir()
    with pytest.raises(RuntimeError, match="budget"):
        runtime.invoke("implementer", "x", artifact)
    assert runtime.max_repairs == 2


def test_status_is_local_and_makes_no_subprocess_calls(tmp_path: Path):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent/TASKS.md").write_text(TASKS)
    def no_process(*args, **kwargs):
        raise AssertionError("status must not invoke a subprocess or model")
    assert ForgeRuntime(tmp_path, runner=no_process).status()["next"]["id"] == "T-002"

def test_agent_invocation_uses_outer_docker_sandbox_without_nested_workspace_sandbox(tmp_path: Path):
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        output_index = command.index("-o") + 1
        container_output = command[output_index]
        local_output = tmp_path / Path(container_output).relative_to("/workspace")
        local_output.parent.mkdir(parents=True, exist_ok=True)
        local_output.write_text('{"result":"PASS","findings":[]}')
        return subprocess.CompletedProcess(command, 0, "", "")

    artifact = tmp_path / "artifact"
    artifact.mkdir()
    prompts = tmp_path / "agent_runtime/prompts"
    prompts.mkdir(parents=True)
    (prompts / "reviewer.txt").write_text("Return exactly JSON")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "run-locked.sh").write_text("#!/usr/bin/env bash\n")

    ForgeRuntime(tmp_path, runner=runner).invoke("reviewer", "packet", artifact)

    command = commands[0]
    sandbox_values = [
        command[i + 1]
        for i, value in enumerate(command[:-1])
        if value == "--sandbox"
    ]
    assert "danger-full-access" in sandbox_values
    assert "workspace-write" not in sandbox_values


def test_run_stops_before_review_when_implementer_makes_no_changes(tmp_path: Path, monkeypatch):
    runtime = ForgeRuntime(tmp_path)
    task = Task(
        "T-999",
        False,
        "Routine safe task.",
        (),
        Classification.SAFE_INCREMENTAL,
    )

    monkeypatch.setattr(runtime, "dirty_paths", lambda: set())
    monkeypatch.setattr(runtime, "make_artifacts", lambda task: tmp_path / "artifacts")
    (tmp_path / "artifacts").mkdir()
    monkeypatch.setattr(runtime, "_context_packet", lambda task, dirty: "packet")
    monkeypatch.setattr(runtime, "invoke", lambda role, prompt, artifacts: "blocked")
    monkeypatch.setattr(runtime, "task_touched_paths", lambda preexisting: set())

    def fake_git(*args):
        return subprocess.CompletedProcess(("git", *args), 0, "", "")

    monkeypatch.setattr(runtime, "_git", fake_git)

    result = runtime.run_task(task)

    assert result["result"] == "IMPLEMENTER_NO_CHANGES"
    assert result["touched_files"] == []

