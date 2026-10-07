import os

from environment import load_environment


def test_load_environment_reads_dotenv_file(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("INVESTIGATOR_TEST_VALUE=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("INVESTIGATOR_TEST_VALUE", raising=False)

    loaded = load_environment(env_path)

    assert loaded is True
    assert os.environ["INVESTIGATOR_TEST_VALUE"] == "from-dotenv"


def test_load_environment_does_not_replace_exported_value(
    tmp_path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("INVESTIGATOR_TEST_VALUE=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("INVESTIGATOR_TEST_VALUE", "already-exported")

    load_environment(env_path)

    assert os.environ["INVESTIGATOR_TEST_VALUE"] == "already-exported"
