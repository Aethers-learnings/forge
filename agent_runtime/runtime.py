"""Small deterministic controller around isolated Codex subprocesses.

This module deliberately owns task selection, safety gates, tests, git scope, and
records.  A model is only asked to plan, implement, review, or repair a compact
packet; it never decides governance or which files to stage.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable


TASK_RE = re.compile(r"^- \[(?P<done>[ xX])\] (?P<id>T-\d+)\s+—\s+(?P<body>.+)$")
ID_RE = re.compile(r"\bT-\d+\b")
CLASS_RE = re.compile(r"Classification:\s*(SAFE_INCREMENTAL|MAJOR_REVIEW|HUMAN_APPROVAL_REQUIRED)\.")
UNSAFE_TERMS = ("destructive migration", "framework replacement", "backend replacement", "fundamental authentication", "irreversible operation", "removal of major subsystem")
RECORD_PATHS = {"agent/SESSION_LOG.md", "agent/TEST_RESULTS.md", "agent/STATE.md", "agent/TASKS.md"}


class Classification(str, Enum):
    SAFE_INCREMENTAL = "SAFE_INCREMENTAL"
    MAJOR_REVIEW = "MAJOR_REVIEW"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


@dataclass(frozen=True)
class Task:
    id: str
    complete: bool
    title: str
    dependencies: tuple[str, ...]
    classification: Classification


@dataclass(frozen=True)
class CheckResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def parse_tasks(text: str) -> list[Task]:
    """Parse Forge's one-line backlog entries without guessing malformed metadata."""
    tasks: list[Task] = []
    for line in text.splitlines():
        match = TASK_RE.match(line)
        if not match:
            continue
        body = match.group("body")
        classification = CLASS_RE.search(body)
        if not classification:
            raise ValueError(f"{match.group('id')} is missing a valid Classification")
        depends = body.split("Depends on:", 1)
        dependencies = tuple(ID_RE.findall(depends[1].split("Classification:", 1)[0])) if len(depends) == 2 else ()
        title = body.split("Depends on:", 1)[0].split("Classification:", 1)[0].strip()
        tasks.append(Task(match.group("id"), match.group("done").lower() == "x", title, dependencies, Classification(classification.group(1))))
    if not tasks:
        raise ValueError("No task entries found")
    return tasks


def dependency_satisfied(task: Task, tasks: Iterable[Task]) -> bool:
    complete = {item.id for item in tasks if item.complete}
    return all(dep in complete for dep in task.dependencies)


def next_safe_task(tasks: list[Task]) -> Task | None:
    return next((task for task in tasks if not task.complete and task.classification is Classification.SAFE_INCREMENTAL and dependency_satisfied(task, tasks)), None)


def parse_reviewer_result(raw: str) -> dict:
    """Strictly parse the only reviewer response accepted by the controller."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Reviewer response is not JSON") from exc
    if not isinstance(value, dict) or set(value) - {"result", "findings"} or set(value) != {"result", "findings"}:
        raise ValueError("Reviewer response must contain only result and findings")
    if value["result"] not in {"PASS", "NEEDS_CHANGES"} or not isinstance(value["findings"], list):
        raise ValueError("Reviewer response has an invalid result or findings")
    return value


def model_routing(env: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ if env is None else env
    return {
        "planner": env.get("FORGE_AUTO_MODEL_PLANNER", "gpt-5.6-luna"),
        "implementer": env.get("FORGE_AUTO_MODEL_IMPLEMENTER", "gpt-5.6-terra"),
        "docs_implementer": env.get("FORGE_AUTO_MODEL_DOCS", "gpt-5.6-luna"),
        "reviewer": env.get("FORGE_AUTO_MODEL_REVIEWER", "gpt-5.6-luna"),
        "security_reviewer": env.get("FORGE_AUTO_MODEL_SECURITY_REVIEWER", "gpt-5.6-sol"),
        "repair": env.get("FORGE_AUTO_MODEL_REPAIR", "gpt-5.6-terra"),
    }


class ForgeRuntime:
    def __init__(self, root: Path | str, *, env: dict[str, str] | None = None, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.root = Path(root).resolve()
        self.env = dict(os.environ if env is None else env)
        self.runner = runner
        self.max_calls = int(self.env.get("FORGE_AUTO_MAX_CALLS", "4"))
        self.max_repairs = int(self.env.get("FORGE_AUTO_MAX_REPAIRS", "2"))
        self.max_prompt_chars = int(self.env.get("FORGE_AUTO_MAX_PROMPT_CHARS", "24000"))
        self.max_diff_chars = int(self.env.get("FORGE_AUTO_MAX_DIFF_CHARS", "16000"))
        self.max_output_chars = int(self.env.get("FORGE_AUTO_MAX_OUTPUT_CHARS", "12000"))
        self.agent_timeout_seconds = int(self.env.get("FORGE_AUTO_AGENT_TIMEOUT", "300"))
        self.calls = 0

    def tasks(self) -> list[Task]:
        return parse_tasks((self.root / "agent/TASKS.md").read_text())

    def status(self) -> dict:
        tasks = self.tasks()
        return {"complete": sum(task.complete for task in tasks), "incomplete": sum(not task.complete for task in tasks), "next": asdict(next_safe_task(tasks)) if next_safe_task(tasks) else None}

    def safety_gate(self, task: Task) -> None:
        if task.classification is not Classification.SAFE_INCREMENTAL:
            raise PermissionError(f"{task.id} is {task.classification.value}; no files will be modified")
        lowered = task.title.lower()
        if any(term in lowered for term in UNSAFE_TERMS):
            raise PermissionError(f"{task.id} matches a protected governance boundary")

    def dirty_paths(self) -> set[str]:
        result = self._git("status", "--porcelain=v1", "-z")
        if result.returncode:
            raise RuntimeError(result.stderr)
        paths: set[str] = set()
        for entry in result.stdout.split("\0"):
            if entry:
                paths.add(entry[3:])
        return paths

    def changed_paths(self) -> set[str]:
        result = self._git("diff", "--name-only", "HEAD")
        if result.returncode:
            raise RuntimeError(result.stderr)
        return {line for line in result.stdout.splitlines() if line}

    def task_touched_paths(self, preexisting: set[str]) -> set[str]:
        """Return paths newly dirty since the snapshot, including untracked files."""
        return self.dirty_paths() - preexisting

    def select_checks(self, changed: set[str]) -> list[tuple[str, ...]]:
        checks: list[tuple[str, ...]] = [("git", "diff", "--check")]
        python_files = [path for path in changed if path.endswith(".py")]
        if python_files:
            checks.append((self._project_python(), "-m", "py_compile", *sorted(python_files)))
        if any(path == "forge_backend.py" or path.startswith("tests/") for path in changed):
            checks.append((self._project_python(), "-m", "pytest", "-q"))
        if any(path.startswith("static/") for path in changed):
            checks.append(("node", "tests/csrf_frontend.cjs"))
        if any(path.startswith("mobile/") for path in changed):
            checks.extend((("npm", "test", "--prefix", "mobile"), ("npm", "run", "lint", "--prefix", "mobile"), ("npx", "tsc", "--noEmit", "-p", "mobile")))
        return checks

    def _project_python(self) -> str:
        """Prefer Forge's managed Python environments for deterministic checks."""
        for relative in (".venv-host/bin/python", ".venv/bin/python"):
            candidate = self.root / relative
            if candidate.is_file():
                return str(candidate)
        return sys.executable

    def run_checks(self, changed: set[str], artifacts: Path) -> list[CheckResult]:
        results: list[CheckResult] = []
        checks_dir = artifacts / "checks"
        checks_dir.mkdir(parents=True, exist_ok=True)
        for number, command in enumerate(self.select_checks(changed), 1):
            result = self.runner(command, cwd=self.root, text=True, capture_output=True, check=False)
            record = CheckResult(tuple(command), result.returncode, result.stdout, result.stderr)
            results.append(record)
            (checks_dir / f"{number:02d}.log").write_text(json.dumps(asdict(record), indent=2))
        return results

    def make_artifacts(self, task: Task) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.root / ".forge-agent/runs" / f"{stamp}-{task.id}"
        path.mkdir(parents=True, exist_ok=False)
        (path / "task.json").write_text(json.dumps(asdict(task), indent=2, default=str))
        return path

    def invoke(self, role: str, prompt: str, artifacts: Path) -> str:
        if self.calls >= self.max_calls:
            raise RuntimeError(f"Model-call budget exhausted ({self.max_calls})")

        routes = model_routing(self.env)
        model = routes[role]
        call_number = self.calls + 1
        output = artifacts / f"{role}-{call_number}.txt"
        template_name = "reviewer" if role == "security_reviewer" else role
        template = self.root / "agent_runtime/prompts" / f"{template_name}.txt"
        instructions = template.read_text().strip() if template.exists() else ""
        combined_prompt = f"{instructions}\n\n{prompt}".strip()

        if len(combined_prompt) > self.max_prompt_chars:
            raise RuntimeError(
                f"Refusing oversized model prompt: {len(combined_prompt)} chars "
                f"(limit {self.max_prompt_chars})"
            )

        sandbox_runner = self.root / "sandbox/run-locked.sh"
        if not sandbox_runner.is_file():
            raise RuntimeError("sandbox/run-locked.sh is missing")

        container_output = Path("/workspace") / output.relative_to(self.root)
        command = (
            str(sandbox_runner),
            "agent",
            "exec",
            "--ephemeral",
            "--sandbox",
            "danger-full-access",
            "-C",
            "/workspace",
            "-m",
            model,
            "-c",
            'model_reasoning_effort="none"',
            "-o",
            str(container_output),
            combined_prompt,
        )

        self.calls += 1
        try:
            result = self.runner(
                command,
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.agent_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            (artifacts / f"{role}-{call_number}.stderr.txt").write_text(
                f"Agent timed out after {self.agent_timeout_seconds}s\n"
            )
            raise RuntimeError(
                f"{role} exceeded {self.agent_timeout_seconds}s agent timeout"
            ) from exc

        (artifacts / f"{role}-{call_number}.stderr.txt").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{role} subprocess failed: {result.returncode}")

        response = output.read_text() if output.exists() else ""
        if len(response) > self.max_output_chars:
            raise RuntimeError(
                f"{role} output exceeded {self.max_output_chars} characters"
            )
        return response

    def invoke_guarded(self, role: str, prompt: str, artifacts: Path) -> str:
        """Invoke an agent while keeping Git history and records controller-owned."""
        before_head = self._git("rev-parse", "HEAD")
        if before_head.returncode:
            raise RuntimeError("Unable to snapshot HEAD before agent invocation")
        before_sha = before_head.stdout.strip()

        record_snapshots = {}
        for relative in RECORD_PATHS:
            path = self.root / relative
            record_snapshots[relative] = path.read_bytes() if path.exists() else None

        try:
            return self.invoke(role, prompt, artifacts)
        finally:
            # Workers never own staging. Preserve their working-tree edits.
            staged = self._git("diff", "--cached", "--name-only")
            if staged.returncode:
                raise RuntimeError("Unable to inspect staged files after agent invocation")
            if staged.stdout.splitlines():
                unstaged = self._git("restore", "--staged", "--", ".")
                if unstaged.returncode:
                    raise RuntimeError(
                        "Agent staged files and controller could not safely unstage them"
                    )

            # Workers may read these records but completion state is deterministic
            # controller output written only after review/check success.
            for relative, original in record_snapshots.items():
                path = self.root / relative
                if original is None:
                    if path.exists():
                        path.unlink()
                elif not path.exists() or path.read_bytes() != original:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(original)

            after_head = self._git("rev-parse", "HEAD")
            if after_head.returncode or after_head.stdout.strip() != before_sha:
                raise RuntimeError(
                    f"{role} changed repository HEAD; agents must not commit or rewrite history"
                )

    def validate_staging(self, allowed: set[str], preexisting: set[str]) -> None:
        result = self._git("diff", "--cached", "--name-only")
        staged = {line for line in result.stdout.splitlines() if line}
        illegal = staged - allowed
        protected = staged & preexisting
        if illegal or protected:
            raise RuntimeError(f"Refusing unsafe staged files: {sorted(illegal | protected)}")

    def stage_and_commit(self, task: Task, touched: set[str], preexisting: set[str]) -> str:
        allowed = touched | RECORD_PATHS
        self.validate_staging(allowed, preexisting)
        paths = sorted(touched & allowed)
        if not paths:
            raise RuntimeError("No autonomous task files to commit")
        staged = self._git("add", "--", *paths)
        if staged.returncode:
            raise RuntimeError(staged.stderr)
        self.validate_staging(allowed, preexisting)
        commit = self._git("-c", "user.name=Forge Agent", "-c", "user.email=forge-agent@local", "commit", "-m", f"chore(agent): complete {task.id}")
        if commit.returncode:
            raise RuntimeError(commit.stderr)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def run_task(self, task: Task) -> dict:
        """Execute the bounded normal flow; all branching outside models is deterministic."""
        self.safety_gate(task)
        preexisting = self.dirty_paths()
        if preexisting:
            raise RuntimeError(
                "Refusing autonomous execution with pre-existing dirty files: "
                + ", ".join(sorted(preexisting))
            )
        if self._git("diff", "--cached", "--name-only").stdout.splitlines():
            raise RuntimeError("Refusing a run with pre-existing staged files")
        artifacts = self.make_artifacts(task)
        context = self._context_packet(task, preexisting)
        (artifacts / "context.txt").write_text(context)
        if self.env.get("FORGE_AUTO_PLAN", "0") == "1":
            self.invoke_guarded("planner", context, artifacts)
        self.invoke_guarded(self._implementation_role(task), context, artifacts)
        touched = self.task_touched_paths(preexisting)
        if not touched:
            return self._finish(
                artifacts,
                "IMPLEMENTER_NO_CHANGES",
                touched,
                [],
                0,
            )
        checks = self.run_checks(touched, artifacts)
        repairs = 0
        while not all(check.passed for check in checks):
            if repairs >= self.max_repairs:
                return self._finish(artifacts, "FAILED_CHECKS", touched, checks, repairs)
            self.invoke_guarded("repair", context + "\nDeterministic check failures:\n" + self._check_summary(checks), artifacts)
            repairs += 1
            touched = self.task_touched_paths(preexisting)
            checks = self.run_checks(touched, artifacts)
        reviewer_role = self._reviewer_role(task)
        review = parse_reviewer_result(self.invoke_guarded(reviewer_role, context + "\nDiff:\n" + self._diff() + "\nChecks:\n" + self._check_summary(checks), artifacts))
        (artifacts / "review.json").write_text(json.dumps(review, indent=2))
        while review["result"] == "NEEDS_CHANGES":
            if repairs >= self.max_repairs:
                return self._finish(artifacts, "REVIEW_LIMIT", touched, checks, repairs, review)
            self.invoke_guarded("repair", context + "\nReviewer findings:\n" + json.dumps(review["findings"]), artifacts)
            repairs += 1
            touched = self.task_touched_paths(preexisting)
            checks = self.run_checks(touched, artifacts)
            if not all(check.passed for check in checks):
                continue  # Never spend a reviewer call while deterministic checks fail.
            review = parse_reviewer_result(self.invoke_guarded(reviewer_role, context + "\nDiff:\n" + self._diff() + "\nChecks:\n" + self._check_summary(checks), artifacts))
            (artifacts / "review.json").write_text(json.dumps(review, indent=2))
        touched = self.task_touched_paths(preexisting)
        final_checks = self.run_checks(touched, artifacts)
        if not all(check.passed for check in final_checks):
            return self._finish(
                artifacts,
                "FINAL_CHECKS_FAILED",
                touched,
                final_checks,
                repairs,
                review,
            )

        # Completion records are controller-owned and written only after the
        # implementation, deterministic checks, and reviewer have all passed.
        self._record_success(task, artifacts, final_checks)
        touched = self.task_touched_paths(preexisting)

        record_check_process = self._git("diff", "--check")
        record_check = CheckResult(
            ("git", "diff", "--check"),
            record_check_process.returncode,
            record_check_process.stdout,
            record_check_process.stderr,
        )
        (artifacts / "checks" / "post-record.log").write_text(
            json.dumps(asdict(record_check), indent=2)
        )
        final_checks = [*final_checks, record_check]
        if not record_check.passed:
            return self._finish(
                artifacts,
                "RECORD_CHECK_FAILED",
                touched,
                final_checks,
                repairs,
                review,
            )

        sha = self.stage_and_commit(task, touched, preexisting)
        return self._finish(
            artifacts,
            "COMMITTED",
            touched,
            final_checks,
            repairs,
            review,
            sha,
        )

    def _context_packet(self, task: Task, preexisting: set[str]) -> str:
        return "\n".join((
            f"Task: {task.id} — {task.title}",
            f"Classification: {task.classification.value}",
            f"Dependencies: {', '.join(task.dependencies) or 'none'}",
            "Constraints: SAFE_INCREMENTAL only; no architecture, framework, backend, auth, destructive migration, irreversible operation, or major subsystem removal.",
            "Protected pre-existing dirty paths: " + (", ".join(sorted(preexisting)) or "none"),
            "Read relevant source/tests and governing records; do not send or rely on the entire repository documentation.",
            "Do not run git add, git commit, git push, git reset, or alter Git history; the controller owns staging and commits.",
            "Do not edit agent/TASKS.md, agent/STATE.md, agent/TEST_RESULTS.md, or agent/SESSION_LOG.md; the controller owns completion records.",
        ))

    @staticmethod
    def _implementation_role(task: Task) -> str:
        return "docs_implementer" if "documentation" in task.title.lower() and "test" not in task.title.lower() else "implementer"

    @staticmethod
    def _reviewer_role(task: Task) -> str:
        sensitive = ("security", "csrf", "authentication", "authorization", "upload", "secret", "token")
        return "security_reviewer" if any(word in task.title.lower() for word in sensitive) else "reviewer"

    def _record_success(self, task: Task, artifacts: Path, checks: list[CheckResult]) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        check_summary = self._check_summary(checks)

        tasks_path = self.root / "agent/TASKS.md"
        tasks_text = tasks_path.read_text()
        incomplete = f"- [ ] {task.id} "
        complete = f"- [x] {task.id} "
        if incomplete not in tasks_text:
            raise RuntimeError(f"Could not mark {task.id} complete in agent/TASKS.md")
        tasks_path.write_text(tasks_text.replace(incomplete, complete, 1))

        with (self.root / "agent/SESSION_LOG.md").open("a") as handle:
            handle.write(
                f"\n- {timestamp}: autonomous {task.id} completed after reviewer PASS; "
                f"artifacts `{artifacts.relative_to(self.root)}`; checks: {check_summary}.\n"
            )

        with (self.root / "agent/TEST_RESULTS.md").open("a") as handle:
            handle.write(
                f"\n## {timestamp} — {task.id} autonomous verification\n\n"
                f"- Reviewer: PASS\n"
                f"- Deterministic checks: {check_summary}\n"
                f"- Run artifacts: `{artifacts.relative_to(self.root)}`\n"
            )

        remaining = next_safe_task(self.tasks())
        next_text = remaining.id if remaining else "none currently eligible"
        with (self.root / "agent/STATE.md").open("a") as handle:
            handle.write(
                f"\n## {timestamp} — Autonomous {task.id}\n\n"
                f"- {task.id} completed with reviewer PASS and deterministic checks passing.\n"
                f"- Next dependency-satisfied SAFE_INCREMENTAL task: {next_text}.\n"
            )

    def _diff(self) -> str:
        result = self._git("diff", "--", ".")
        diff = result.stdout
        if len(diff) > self.max_diff_chars:
            raise RuntimeError(
                f"Refusing oversized reviewer diff: {len(diff)} chars "
                f"(limit {self.max_diff_chars})"
            )
        return diff

    @staticmethod
    def _check_summary(checks: list[CheckResult]) -> str:
        return "; ".join(f"{' '.join(check.command)} => {check.returncode}" for check in checks)

    def _finish(self, artifacts: Path, result: str, touched: set[str], checks: list[CheckResult], repairs: int, review: dict | None = None, sha: str | None = None) -> dict:
        final = {"result": result, "touched_files": sorted(touched), "repairs": repairs, "model_calls": self.calls, "checks_passed": all(item.passed for item in checks), "review": review, "commit": sha}
        (artifacts / "touched-files.json").write_text(json.dumps(sorted(touched), indent=2))
        if not (artifacts / "review.json").exists():
            (artifacts / "review.json").write_text(json.dumps(review or {"result": "NOT_RUN", "findings": []}, indent=2))
        (artifacts / "final-result.json").write_text(json.dumps(final, indent=2))
        return final

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.runner(("git", *args), cwd=self.root, text=True, capture_output=True, check=False)
