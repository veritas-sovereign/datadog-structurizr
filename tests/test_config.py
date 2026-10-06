import pytest

from datadog_structurizr.config import load_config


def test_online_requires_keys_service_and_env():
    with pytest.raises(SystemExit) as exc:
        load_config({})
    for name in ("DD_SERVICE", "DD_ENV", "DD_API_KEY", "DD_APP_KEY"):
        assert name in str(exc.value)


def test_offline_does_not_need_keys(tmp_path):
    cfg = load_config({"DD_SERVICE": "s", "DD_ENV": "prod", "OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")})
    assert cfg.offline and cfg.raw_dir.is_dir()


def test_cli_values_override_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DD_SERVICE", "from-env")
    monkeypatch.setenv("DD_ENV", "staging")
    cfg = load_config({"DD_SERVICE": "from-cli", "OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")})
    assert (cfg.service, cfg.env, cfg.site, cfg.lookback_hours) == ("from-cli", "staging", "datadoghq.com", 24)


def _write(tmp_path, text):
    path = tmp_path / "c4.toml"
    path.write_text(text)
    return path


def test_config_file_supplies_inputs(tmp_path):
    path = _write(tmp_path, '''
service = "web"
env = "prod"
hours = 6
ignore = ["otel-*"]
[system]
name = "Shop"
include = ["web-worker"]
[person]
name = "Shopper"
[classify]
datastores = ["ledger"]
''')
    cfg = load_config({"OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")}, config_file=path)
    assert (cfg.service, cfg.env, cfg.lookback_hours) == ("web", "prod", 6)
    assert (cfg.system_name, cfg.include, cfg.ignore) == ("Shop", ("web-worker",), ("otel-*",))
    assert (cfg.person_enabled, cfg.person_name, cfg.datastores) == (True, "Shopper", ("ledger",))


def test_cli_beats_file_beats_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DD_SERVICE", "from-env")
    monkeypatch.setenv("DD_ENV", "from-env")
    path = _write(tmp_path, 'service = "from-file"\nenv = "from-file"\n[system]\nname = "File"\n')
    cfg = load_config({"DD_SERVICE": "from-cli", "SYSTEM_NAME": "Cli", "OFFLINE": "1",
                       "OUTPUT_DIR": str(tmp_path / "o")}, config_file=path)
    assert (cfg.service, cfg.env, cfg.system_name) == ("from-cli", "from-file", "Cli")


def test_include_merges_file_and_cli_without_duplicates_or_target(tmp_path):
    path = _write(tmp_path, 'service = "web"\nenv = "prod"\n[system]\ninclude = ["a", "b"]\n')
    cfg = load_config({"INCLUDE": ("b", "c", "web"), "OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")},
                      config_file=path)
    assert cfg.include == ("a", "b", "c")


def test_person_can_be_turned_off_from_file_or_cli(tmp_path):
    path = _write(tmp_path, 'service = "web"\nenv = "prod"\n[person]\nenabled = false\n')
    common = {"OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")}
    assert not load_config(common, config_file=path).person_enabled
    assert not load_config({**common, "DD_SERVICE": "w", "DD_ENV": "p", "NO_PERSON": "1"}).person_enabled


def test_component_cap_from_file(tmp_path):
    path = _write(tmp_path, 'service = "web"\nenv = "prod"\n[components]\nmax = 4\n')
    assert load_config({"OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")}, config_file=path).max_components == 4
    assert load_config({"OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o"),
                        "DD_SERVICE": "w", "DD_ENV": "p"}).max_components == 12


@pytest.mark.parametrize("text, message", [
    ('servce = "web"', "unknown key 'servce'"),
    ('[system]\nnmae = "x"', "unknown key 'nmae'"),
    ('api_key = "secret"', "not allowed here"),
    ('[system]\ninclude = "web-worker"', "must be a list of strings"),
    ('hours = "24"', "must be int"),
    ('hours = true', "must be int"),
    ('[person]\nenabled = "no"', "must be bool"),
    ('system = "x"', "must be a table"),
    ('service = ', "invalid TOML"),
    ('[components]\nmax = "12"', "must be int"),
    ('[components]\nmax = 1', "at least 2"),
])
def test_config_file_errors(tmp_path, text, message):
    with pytest.raises(SystemExit, match=message):
        load_config({"OFFLINE": "1"}, config_file=_write(tmp_path, text))


def test_missing_config_file(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        load_config({}, config_file=tmp_path / "nope.toml")


def test_prompts_for_missing_service_and_env(tmp_path):
    answers = iter(["  web  ", "prod"])
    asked = []

    def prompt(question):
        asked.append(question)
        return next(answers)

    cfg = load_config({"OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")}, prompt=prompt)
    assert (cfg.service, cfg.env) == ("web", "prod")
    assert len(asked) == 2


def test_no_prompt_when_values_given(tmp_path):
    def prompt(question):
        raise AssertionError("should not prompt")

    load_config({"DD_SERVICE": "w", "DD_ENV": "p", "OFFLINE": "1", "OUTPUT_DIR": str(tmp_path / "o")},
                prompt=prompt)
