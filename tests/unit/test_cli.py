from unittest.mock import AsyncMock, patch, Mock, MagicMock
import logging
import pytest
import requests
from tests.constants import ENV_VARS
from tests.utils import build_validation
from spectacles.cli import (
    main,
    create_parser,
    handle_exceptions,
    preprocess_dash,
    process_pin_imports,
)
from spectacles.exceptions import (
    LookerApiError,
    SpectaclesException,
    GenericValidationError,
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ENV_VARS.keys():
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable, value in ENV_VARS.items():
        monkeypatch.setenv(variable, value)


@pytest.fixture
def limited_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable, value in ENV_VARS.items():
        if variable in ["LOOKER_CLIENT_SECRET", "LOOKER_PROJECT"]:
            monkeypatch.delenv(variable, raising=False)
        else:
            monkeypatch.setenv(variable, value)


@patch("sys.argv", new=["spectacles", "--help"])
def test_help():
    with pytest.raises(SystemExit) as cm:
        main()
        assert cm.value.code == 0


@pytest.mark.parametrize(
    "exception,exit_code",
    [(ValueError, 1), (SpectaclesException, 100), (GenericValidationError, 102)],
)
def test_handle_exceptions_unhandled_error(exception: Exception, exit_code: int):
    @handle_exceptions
    def raise_exception():
        if exception == SpectaclesException:
            raise exception(
                name="exception-name",
                title="An exception occurred.",
                detail="Couldn't handle the truth. Please try again.",
            )
        elif exception == GenericValidationError:
            raise GenericValidationError
        else:
            raise exception(f"This is a {exception.__class__.__name__}.")

    with pytest.raises(SystemExit) as pytest_error:
        raise_exception()

    assert pytest_error.value.code == exit_code


def test_handle_exceptions_looker_error_should_log_response_and_status(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.DEBUG)
    response = Mock(spec=requests.Response)
    response.request = Mock(spec=requests.PreparedRequest)
    response.request.url = "https://api.looker.com"
    response.request.method = "GET"
    response.json.return_value = {
        "message": "Not found",
        "documentation_url": "http://docs.looker.com/",
    }
    status = 404

    @handle_exceptions
    def raise_exception():
        raise LookerApiError(
            name="exception-name",
            title="An exception occurred.",
            detail="Couldn't handle the truth. Please try again.",
            status=status,
            response=response,
        )

    with pytest.raises(SystemExit) as pytest_error:
        raise_exception()
    captured = "\n".join(record.msg for record in caplog.records)
    assert str(status) in captured
    assert '"message": "Not found"' in captured
    assert '"documentation_url": "http://docs.looker.com/"' in captured
    assert pytest_error.value.code == 101


def test_parse_args_with_no_arguments_supplied(
    clean_env: None, capsys: pytest.CaptureFixture
):
    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["connect"])
    captured = capsys.readouterr()
    assert (
        "the following arguments are required: --base-url, --client-id, --client-secret"
        in captured.err
    )


def test_parse_args_with_one_argument_supplied(
    clean_env: None, capsys: pytest.CaptureFixture
):
    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["connect", "--base-url", "BASE_URL_CLI"])
    captured = capsys.readouterr()
    assert (
        "the following arguments are required: --client-id, --client-secret"
        in captured.err
    )


def test_parse_args_with_only_cli(clean_env: None):
    parser = create_parser()
    args = parser.parse_args(
        [
            "connect",
            "--base-url",
            "BASE_URL_CLI",
            "--client-id",
            "CLIENT_ID_CLI",
            "--client-secret",
            "CLIENT_SECRET_CLI",
        ]
    )
    assert args.base_url == "BASE_URL_CLI"
    assert args.client_id == "CLIENT_ID_CLI"
    assert args.client_secret == "CLIENT_SECRET_CLI"


@patch("spectacles.cli.YamlConfigAction.parse_config")
def test_parse_args_with_only_config_file(mock_parse_config, clean_env: None):
    parser = create_parser()
    mock_parse_config.return_value = {
        "base_url": "BASE_URL_CONFIG",
        "client_id": "CLIENT_ID_CONFIG",
        "client_secret": "CLIENT_SECRET_CONFIG",
        "project": "spectacles",
        "explores": ["model_a/*", "-model_a/explore_b"],
    }
    args = parser.parse_args(["sql", "--config-file", "config.yml"])
    assert args.base_url == "BASE_URL_CONFIG"
    assert args.client_id == "CLIENT_ID_CONFIG"
    assert args.client_secret == "CLIENT_SECRET_CONFIG"
    assert args.explores == ["model_a/*", "-model_a/explore_b"]


@patch("spectacles.cli.YamlConfigAction.parse_config")
def test_parse_args_with_incomplete_config_file(
    mock_parse_config: MagicMock, clean_env: None, capsys: pytest.CaptureFixture
):
    parser = create_parser()
    mock_parse_config.return_value = {
        "base_url": "BASE_URL_CONFIG",
        "client_id": "CLIENT_ID_CONFIG",
    }
    with pytest.raises(SystemExit):
        parser.parse_args(["connect", "--config-file", "config.yml"])
    captured = capsys.readouterr()
    assert "the following arguments are required: --client-secret" in captured.err


@patch("spectacles.cli.run_sql")
@patch("spectacles.cli.YamlConfigAction.parse_config")
def test_config_file_explores_folders_processed_correctly(
    mock_parse_config: MagicMock, mock_run_sql: AsyncMock, clean_env: None
):
    mock_parse_config.return_value = {
        "base_url": "BASE_URL_CONFIG",
        "client_id": "CLIENT_ID_CONFIG",
        "client_secret": "CLIENT_SECRET_CONFIG",
        "project": "spectacles",
        "explores": ["model_a/*", "-model_a/explore_b"],
    }
    with patch("sys.argv", ["spectacles", "sql", "--config-file", "config.yml"]):
        main()

    assert mock_run_sql.call_args[1]["filters"] == [
        "model_a/*",
        "-model_a/explore_b",
    ]


@patch("spectacles.cli.run_sql")
def test_cli_explores_folders_processed_correctly(
    mock_run_sql: AsyncMock, clean_env: None
):
    with patch(
        "sys.argv",
        [
            "spectacles",
            "sql",
            "--base-url",
            "BASE_URL",
            "--client-id",
            "CLIENT_ID",
            "--client-secret",
            "CLIENT_SECRET",
            "--project",
            "spectacles",
            "--explores",
            "model_a/*",
            "-model_a/explore_b",
        ],
    ):
        main()
    assert mock_run_sql.call_args[1]["filters"] == [
        "model_a/*",
        "-model_a/explore_b",
    ]


def test_parse_args_with_only_env_vars(env: None):
    parser = create_parser()
    args = parser.parse_args(["connect"])
    assert args.base_url == "BASE_URL_ENV_VAR"
    assert args.client_id == "CLIENT_ID_ENV_VAR"
    assert args.client_secret == "CLIENT_SECRET_ENV_VAR"


def test_parse_args_with_incomplete_env_vars(
    limited_env: None, capsys: pytest.CaptureFixture
):
    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["connect"])
    captured = capsys.readouterr()
    assert "the following arguments are required: --client-secret" in captured.err


@patch("spectacles.cli.YamlConfigAction.parse_config")
def test_arg_precedence(mock_parse_config: MagicMock, limited_env: None):
    parser = create_parser()
    # Precedence: command line > environment variables > config files
    mock_parse_config.return_value = {
        "base_url": "BASE_URL_CONFIG",
        "client_id": "CLIENT_ID_CONFIG",
        "client_secret": "CLIENT_SECRET_CONFIG",
    }
    args = parser.parse_args(
        ["connect", "--config-file", "config.yml", "--base-url", "BASE_URL_CLI"]
    )
    assert args.base_url == "BASE_URL_CLI"
    assert args.client_id == "CLIENT_ID_ENV_VAR"
    assert args.client_secret == "CLIENT_SECRET_CONFIG"


def test_env_var_override_argparse_default(env: None):
    parser = create_parser()
    args = parser.parse_args(["connect"])
    assert args.port == 8080


@patch("spectacles.cli.YamlConfigAction.parse_config")
def test_config_override_argparse_default(
    mock_parse_config: MagicMock, clean_env: None
):
    parser = create_parser()
    mock_parse_config.return_value = {
        "base_url": "BASE_URL_CONFIG",
        "client_id": "CLIENT_ID_CONFIG",
        "client_secret": "CLIENT_SECRET_CONFIG",
        "port": 8080,
    }
    args = parser.parse_args(["connect", "--config-file", "config.yml"])
    assert args.port == 8080


@patch("spectacles.cli.YamlConfigAction.parse_config")
def test_bad_config_file_parameter(mock_parse_config: MagicMock, clean_env: None):
    parser = create_parser()
    mock_parse_config.return_value = {
        "base_url": "BASE_URL_CONFIG",
        "api_key": "CLIENT_ID_CONFIG",
        "port": 8080,
    }
    with pytest.raises(
        SpectaclesException, match="Invalid configuration file parameter"
    ):
        parser.parse_args(["connect", "--config-file", "config.yml"])


def test_parse_remote_reset_with_assert(env: None):
    parser = create_parser()
    args = parser.parse_args(["assert", "--remote-reset"])
    assert args.remote_reset


def test_parse_args_with_mutually_exclusive_args_remote_reset(
    env: None, capsys: pytest.CaptureFixture
):
    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["sql", "--commit-ref", "abc123", "--remote-reset"])
    captured = capsys.readouterr()
    assert (
        "argument --remote-reset: not allowed with argument --commit-ref"
        in captured.err
    )


def test_parse_args_with_mutually_exclusive_args_commit_ref(
    env: None, capsys: pytest.CaptureFixture
):
    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["sql", "--remote-reset", "--commit-ref", "abc123"])
    captured = capsys.readouterr()
    assert (
        "argument --commit-ref: not allowed with argument --remote-reset"
        in captured.err
    )


@patch("sys.argv", new=["spectacles", "sql"])
@patch("spectacles.cli.Runner")
@patch("spectacles.cli.LookerClient", autospec=True)
@patch("spectacles.cli.tracking")
def test_main_with_sql_validator(
    mock_tracking: MagicMock,
    mock_client: MagicMock,
    mock_runner: MagicMock,
    env: None,
    caplog: pytest.LogCaptureFixture,
):
    validation = build_validation("sql")
    mock_runner.return_value.validate_sql = AsyncMock(return_value=validation)
    with pytest.raises(SystemExit):
        main()
    mock_tracking.track_invocation_start.assert_called_once_with(
        "BASE_URL_ENV_VAR", "sql", project="PROJECT_ENV_VAR"
    )
    # TODO: Uncomment the below assertion once #262 is fixed
    # mock_tracking.track_invocation_end.assert_called_once()
    mock_runner.assert_called_once()
    assert "ecommerce.orders passed" in caplog.text
    assert "ecommerce.sessions passed" in caplog.text
    assert "ecommerce.users failed" in caplog.text


@patch("sys.argv", new=["spectacles", "content"])
@patch("spectacles.cli.Runner")
@patch("spectacles.cli.LookerClient", autospec=True)
@patch("spectacles.cli.tracking")
def test_main_with_content_validator(
    mock_tracking: MagicMock,
    mock_client: MagicMock,
    mock_runner: MagicMock,
    env: None,
    caplog: pytest.LogCaptureFixture,
):
    validation = build_validation("content")
    mock_runner.return_value.validate_content = AsyncMock(return_value=validation)
    with pytest.raises(SystemExit):
        main()
    mock_tracking.track_invocation_start.assert_called_once_with(
        "BASE_URL_ENV_VAR", "content", project="PROJECT_ENV_VAR"
    )
    # TODO: Uncomment the below assertion once #262 is fixed
    # mock_tracking.track_invocation_end.assert_called_once()
    mock_runner.assert_called_once()
    assert "ecommerce.orders passed" in caplog.text
    assert "ecommerce.sessions passed" in caplog.text
    assert "ecommerce.users failed" in caplog.text


@patch("sys.argv", new=["spectacles", "assert"])
@patch("spectacles.cli.Runner", autospec=True)
@patch("spectacles.cli.LookerClient", autospec=True)
@patch("spectacles.cli.tracking")
def test_main_with_assert_validator(
    mock_tracking: MagicMock,
    mock_client: MagicMock,
    mock_runner: MagicMock,
    env: None,
    caplog: pytest.LogCaptureFixture,
):
    validation = build_validation("assert")
    mock_runner.return_value.validate_data_tests = AsyncMock(return_value=validation)
    with pytest.raises(SystemExit):
        main()
    mock_tracking.track_invocation_start.assert_called_once_with(
        "BASE_URL_ENV_VAR", "assert", project="PROJECT_ENV_VAR"
    )
    # TODO: Uncomment the below assertion once #262 is fixed
    # mock_tracking.track_invocation_end.assert_called_once()
    mock_runner.assert_called_once()
    assert "ecommerce.orders passed" in caplog.text
    assert "ecommerce.sessions passed" in caplog.text
    assert "ecommerce.users failed" in caplog.text


@patch("sys.argv", new=["spectacles", "lookml"])
@patch("spectacles.cli.Runner", autospec=True)
@patch("spectacles.cli.LookerClient", autospec=True)
@patch("spectacles.cli.tracking")
def test_main_with_lookml_validator(
    mock_tracking: MagicMock,
    mock_client: MagicMock,
    mock_runner: MagicMock,
    env: None,
    caplog: pytest.LogCaptureFixture,
):
    validation = build_validation("lookml")
    mock_runner.return_value.validate_lookml = AsyncMock(return_value=validation)
    with pytest.raises(SystemExit):
        main()
    mock_tracking.track_invocation_start.assert_called_once_with(
        "BASE_URL_ENV_VAR", "lookml", project="PROJECT_ENV_VAR"
    )
    # TODO: Uncomment the below assertion once #262 is fixed
    # mock_tracking.track_invocation_end.assert_called_once()
    mock_runner.assert_called_once()
    assert "eye_exam/eye_exam.model.lkml" in caplog.text
    assert "Could not find a field named 'users__fail.first_name'" in caplog.text


@patch("sys.argv", new=["spectacles", "connect"])
@patch("spectacles.cli.run_connect")
@patch("spectacles.cli.tracking")
def test_main_with_connect(
    mock_tracking: MagicMock, mock_run_connect: AsyncMock, env: None
):
    main()
    mock_tracking.track_invocation_start.assert_called_once_with(
        "BASE_URL_ENV_VAR", "connect", project=None
    )
    mock_tracking.track_invocation_end.assert_called_once()
    mock_run_connect.assert_called_once_with(
        base_url="BASE_URL_ENV_VAR",
        client_id="CLIENT_ID_ENV_VAR",
        client_secret="CLIENT_SECRET_ENV_VAR",
        port=8080,
        api_version=3.1,
    )


@patch("sys.argv", new=["spectacles", "connect", "--do-not-track"])
@patch("spectacles.cli.run_connect")
@patch("spectacles.cli.tracking")
def test_main_with_do_not_track(
    mock_tracking: MagicMock, mock_run_connect: AsyncMock, env: None
):
    main()
    mock_tracking.track_invocation_start.assert_not_called()
    mock_tracking.track_invocation_end.assert_not_called()
    mock_run_connect.assert_called_once_with(
        base_url="BASE_URL_ENV_VAR",
        client_id="CLIENT_ID_ENV_VAR",
        client_secret="CLIENT_SECRET_ENV_VAR",
        port=8080,
        api_version=3.1,
    )


def test_process_pin_imports_with_no_refs():
    output = process_pin_imports([])
    assert output == {}


def test_process_pin_imports_with_one_ref():
    output = process_pin_imports(["welcome_to_looker:testing-imports"])
    assert output == {"welcome_to_looker": "testing-imports"}


def test_process_pin_imports_with_multiple_refs():
    output = process_pin_imports(
        ["welcome_to_looker:testing-imports", "eye_exam:123abc"]
    )
    assert output == {"welcome_to_looker": "testing-imports", "eye_exam": "123abc"}


def test_preprocess_dashes_with_folder_ids_should_work():
    args = [
        preprocess_dash(arg)
        for arg in ["--folders", "40", "25", "-41", "-1", "-344828", "3929"]
    ]
    assert args == ["--folders", "40", "25", "~41", "~1", "~344828", "3929"]


def test_preprocess_dashes_with_model_explores_should_work():
    args = [
        preprocess_dash(arg)
        for arg in [
            "--explores",
            "model_a/explore_a",
            "-model_b/explore_b",
            "model_c/explore_c",
            "-model_d/explore_d",
        ]
    ]
    assert args == [
        "--explores",
        "model_a/explore_a",
        "~model_b/explore_b",
        "model_c/explore_c",
        "~model_d/explore_d",
    ]


def test_preprocess_dashes_with_wildcards_should_work():
    args = [
        preprocess_dash(arg)
        for arg in (
            "--explores",
            "*/explore_a",
            "-model_b/*",
            "model-a/explore-a",
            "*/*",
            "-*/*",
        )
    ]
    assert args == [
        "--explores",
        "*/explore_a",
        "~model_b/*",
        "model-a/explore-a",
        "*/*",
        "~*/*",
    ]
