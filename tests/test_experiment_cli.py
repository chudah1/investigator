from types import SimpleNamespace

import pytest

import experiment_cli
from experiment_cli import (
    TrackedResponses,
    _langchain_usage,
    _openai_usage,
    parse_args,
)


class FakeResponses:
    def parse(self, **kwargs):
        return SimpleNamespace(request=kwargs, usage=None)


def test_tracked_responses_preserves_response_for_usage_collection() -> None:
    tracked = TrackedResponses(FakeResponses())

    response = tracked.parse(model="test-model")

    assert tracked.last_response is response
    assert response.request == {"model": "test-model"}


def test_usage_helpers_support_openai_and_langchain_shapes() -> None:
    response = SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
        )
    )
    langchain_usage = {
        "test-model": {
            "input_tokens": 150,
            "output_tokens": 30,
            "total_tokens": 180,
        },
        "other-model": {
            "input_tokens": 50,
            "output_tokens": 10,
            "total_tokens": 60,
        },
    }

    assert _openai_usage(response) == (100, 20, 120)
    assert _langchain_usage(langchain_usage) == (200, 40, 240)


def test_experiment_cli_defaults_to_one_paid_run_per_mode() -> None:
    args = parse_args([])

    assert args.runs == 1
    assert args.modes == ("baseline", "agent")


def test_experiment_cli_rejects_zero_runs() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--runs", "0"])


def test_experiment_cli_loads_environment_before_validation(
    monkeypatch,
    capsys,
) -> None:
    environment_loaded = False

    def fake_load_environment() -> None:
        nonlocal environment_loaded
        environment_loaded = True

    monkeypatch.setattr(
        experiment_cli,
        "load_environment",
        fake_load_environment,
    )

    exit_code = experiment_cli.main(["missing-job"])

    assert exit_code == 2
    assert environment_loaded is True
    assert capsys.readouterr().out.strip() == (
        "No evaluation case for job: missing-job"
    )
