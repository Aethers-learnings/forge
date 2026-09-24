from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_runtime.runtime import Classification, ForgeRuntime, Task, dependency_satisfied, model_routing, next_safe_task, parse_reviewer_result, parse_tasks, run_autopilot


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


def test_autopilot_default_bound_and_fresh_runtime_budget(tmp_path: Path):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent/TASKS.md").write_text("\n".join(
        f"- [ ] T-{number:03d} — Safe {number}. Depends on: none. Classification: SAFE_INCREMENTAL."
        for number in range(1, 5)
    ))
    instances = []

    class FakeRuntime:
        def __init__(self, root):
            self.root = root
            self.calls = 2
            instances.append(self)

        def tasks(self):
            return parse_tasks((self.root / "agent/TASKS.md").read_text())

        def run_task(self, task):
            return {"result": "COMMITTED"}

    summary = run_autopilot(tmp_path, runtime_factory=FakeRuntime)
    assert summary["tasks_attempted"] == 3
    assert summary["total_model_calls"] == 6
    assert len(instances) == 7


def test_autopilot_stops_on_first_non_commit_and_skips_governance(tmp_path: Path):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent/TASKS.md").write_text(
        "- [ ] T-001 — Safe. Depends on: none. Classification: SAFE_INCREMENTAL.\n"
        "- [ ] T-002 — Review. Depends on: none. Classification: MAJOR_REVIEW.\n"
    )
    executed = []

    class FakeRuntime:
        calls = 1
        def __init__(self, root): self.root = root
        def tasks(self): return parse_tasks((self.root / "agent/TASKS.md").read_text())
        def run_task(self, task):
            executed.append(task.id)
            return {"result": "FAILED_CHECKS"}

    summary = run_autopilot(tmp_path, 3, runtime_factory=FakeRuntime)
    assert executed == ["T-001"]
    assert summary["result"] == "FAILED_CHECKS"
    # Failed work remains incomplete, so it is still the next eligible task.
    assert summary["next_eligible_task"] == "T-001"


def test_autopilot_no_eligible_task_is_clean(tmp_path: Path):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent/TASKS.md").write_text("- [ ] T-001 — Review. Depends on: none. Classification: HUMAN_APPROVAL_REQUIRED.\n")
    summary = run_autopilot(tmp_path, runtime_factory=ForgeRuntime)
    assert summary["result"] == "COMPLETED"
    assert summary["tasks_attempted"] == 0
    assert summary["next_eligible_task"] is None


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
    assert command[1] == "agent"
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


def test_project_python_prefers_host_venv(tmp_path: Path):
    python = tmp_path / ".venv-host/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("")

    runtime = ForgeRuntime(tmp_path)
    checks = runtime.select_checks({"forge_backend.py"})

    assert any(
        command[:3] == (str(python), "-m", "pytest")
        for command in checks
    )


def test_guarded_agent_unstages_worker_changes_without_discarding_them(tmp_path: Path, monkeypatch):
    runtime = ForgeRuntime(tmp_path)
    calls = []

    monkeypatch.setattr(runtime, "invoke", lambda role, prompt, artifacts: "ok")

    def fake_git(*args):
        calls.append(args)
        if args == ("rev-parse", "HEAD"):
            return subprocess.CompletedProcess(args, 0, "abc123\\n", "")
        if args == ("diff", "--cached", "--name-only"):
            return subprocess.CompletedProcess(args, 0, "forge_backend.py\\n", "")
        if args == ("restore", "--staged", "--", "."):
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(runtime, "_git", fake_git)

    assert runtime.invoke_guarded("implementer", "packet", tmp_path) == "ok"
    assert ("restore", "--staged", "--", ".") in calls


def test_guarded_agent_rejects_worker_commit(tmp_path: Path, monkeypatch):
    runtime = ForgeRuntime(tmp_path)
    heads = iter(("before\\n", "after\\n"))

    monkeypatch.setattr(runtime, "invoke", lambda role, prompt, artifacts: "ok")

    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return subprocess.CompletedProcess(args, 0, next(heads), "")
        if args == ("diff", "--cached", "--name-only"):
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(runtime, "_git", fake_git)

    import pytest
    with pytest.raises(RuntimeError, match="changed repository HEAD"):
        runtime.invoke_guarded("implementer", "packet", tmp_path)


def test_record_success_marks_task_and_writes_controller_records(tmp_path: Path):
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "TASKS.md").write_text(
        "- [ ] T-999 — Safe thing. Depends on: none. Classification: SAFE_INCREMENTAL.\\n"
    )
    for name in ("STATE.md", "TEST_RESULTS.md", "SESSION_LOG.md"):
        (agent / name).write_text("")

    artifacts = tmp_path / ".forge-agent/runs/example-T-999"
    artifacts.mkdir(parents=True)

    runtime = ForgeRuntime(tmp_path)
    task = Task("T-999", False, "Safe thing.", (), Classification.SAFE_INCREMENTAL)
    runtime._record_success(task, artifacts, [])

    assert "- [x] T-999 " in (agent / "TASKS.md").read_text()
    assert "T-999 completed" in (agent / "STATE.md").read_text()
    assert "Reviewer: PASS" in (agent / "TEST_RESULTS.md").read_text()
    assert "reviewer PASS" in (agent / "SESSION_LOG.md").read_text()

def test_guarded_agent_restores_controller_owned_records(tmp_path: Path, monkeypatch):
    agent = tmp_path / "agent"
    agent.mkdir()
    originals = {
        "TASKS.md": "original tasks\n",
        "STATE.md": "original state\n",
        "TEST_RESULTS.md": "original tests\n",
        "SESSION_LOG.md": "original session\n",
    }
    for name, content in originals.items():
        (agent / name).write_text(content)

    runtime = ForgeRuntime(tmp_path)

    def fake_invoke(role, prompt, artifacts):
        for name in originals:
            (agent / name).write_text("worker changed this\n")
        return "ok"

    monkeypatch.setattr(runtime, "invoke", fake_invoke)

    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return subprocess.CompletedProcess(args, 0, "abc123\n", "")
        if args == ("diff", "--cached", "--name-only"):
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(runtime, "_git", fake_git)

    assert runtime.invoke_guarded("implementer", "packet", tmp_path) == "ok"

    for name, content in originals.items():
        assert (agent / name).read_text() == content
