from typing import Any

import cli
from database import Database
from models import InvestigationResult
from repository import Repository
from seed import seed_database


def empty_result() -> InvestigationResult:
    return InvestigationResult(
        job_id="job-001",
        findings=[],
        unresolved_questions=[],
        recommended_actions=[],
    )


class FakeGraph:
    def __init__(self, result: InvestigationResult) -> None:
        self.result = result
        self.input: dict[str, Any] | None = None
        self.config: dict[str, Any] | None = None

    def invoke(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        self.input = graph_input
        self.config = config
        return {"result": self.result}


def test_investigate_with_agent_invokes_graph_with_job(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    repository = Repository(Database(str(db_path)))
    expected = empty_result()
    graph = FakeGraph(expected)
    fake_model = object()

    monkeypatch.setattr(cli, "create_agent_model", lambda _name: fake_model)
    monkeypatch.setattr(
        cli,
        "build_investigation_graph",
        lambda model, repo: graph,
    )

    result = cli.investigate_with_agent(
        repository,
        "job-001",
        "test-model",
    )

    assert result == expected
    assert graph.input is not None
    assert graph.input["job_id"] == "job-001"
    assert graph.input["messages"][0].content == (
        "Investigate report delivery job job-001."
    )
    assert graph.config == {
        "recursion_limit": cli.MAX_TOOL_CALLS * 2 + 5
    }


def test_cli_agent_mode_prints_structured_result(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    expected = empty_result()
    received: dict[str, str] = {}

    def fake_investigate(
        _repository: Repository,
        job_id: str,
        model_name: str,
    ) -> InvestigationResult:
        received["job_id"] = job_id
        received["model_name"] = model_name
        return expected

    monkeypatch.setattr(cli, "investigate_with_agent", fake_investigate)

    exit_code = cli.main(
        [
            "job-001",
            "--db",
            str(db_path),
            "--mode",
            "agent",
            "--model",
            "test-model",
        ]
    )

    assert exit_code == 0
    assert received == {
        "job_id": "job-001",
        "model_name": "test-model",
    }
    assert '"job_id": "job-001"' in capsys.readouterr().out


def test_cli_returns_before_model_call_for_unknown_job(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "investigator.db"
    Database(str(db_path)).initialize()

    def unexpected_call(*_args: Any, **_kwargs: Any) -> InvestigationResult:
        raise AssertionError("The model must not be called for an unknown job.")

    monkeypatch.setattr(cli, "investigate_with_agent", unexpected_call)

    exit_code = cli.main(
        ["missing-job", "--db", str(db_path), "--mode", "agent"]
    )

    assert exit_code == 1
    assert capsys.readouterr().out.strip() == "Job not found: missing-job"
