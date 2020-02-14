from pathlib import Path
import json
from unittest.mock import patch, Mock
import pytest
from spectacles.lookml import Project, Model, Explore, Dimension
from spectacles.client import LookerClient
from spectacles.validators import SqlValidator

TEST_BASE_URL = "https://test.looker.com"
TEST_CLIENT_ID = "test_client_id"
TEST_CLIENT_SECRET = "test_client_secret"


def load(filename):
    """Helper method to load a JSON file from tests/resources and parse it."""
    path = Path(__file__).parent / "resources" / filename
    with path.open() as file:
        return json.load(file)


@pytest.fixture
def client(monkeypatch):
    mock_authenticate = Mock(spec=LookerClient.authenticate)
    monkeypatch.setattr(LookerClient, "authenticate", mock_authenticate)
    return LookerClient(TEST_BASE_URL, TEST_CLIENT_ID, TEST_CLIENT_SECRET)


@pytest.fixture
def validator(client):
    return SqlValidator(client=client, project="test_project")


@pytest.fixture
def project():
    dimensions = [
        Dimension(
            "test_view.dimension_one",
            "number",
            "${TABLE}.dimension_one",
            (
                "https://test.looker.com/projects/spectacles/"
                "files/test_view.view.lkml?line=340"
            ),
        ),
        Dimension(
            "test_view.dimension_two",
            "number",
            "${TABLE}.dimension_two",
            (
                "https://test.looker.com/projects/spectacles/"
                "files/test_view.view.lkml?line=360"
            ),
        ),
    ]
    explores_model_one = [Explore("test_explore_one", dimensions)]
    explores_model_two = [Explore("test_explore_two", dimensions)]
    models = [
        Model("test_model_one", "test_project", explores_model_one),
        Model("test_model.two", "test_project", explores_model_two),
    ]
    project = Project("test_project", models)
    return project


@patch("spectacles.client.LookerClient.get_lookml_dimensions")
@patch("spectacles.client.LookerClient.get_lookml_models")
def test_build_project(mock_get_models, mock_get_dimensions, project, validator):
    mock_get_models.return_value = load("response_models.json")
    mock_get_dimensions.return_value = load("response_dimensions.json")
    validator.build_project(selectors=["*/*"])
    assert validator.project == project


def test_extract_error_details_error_dict(validator):
    message = "An error message."
    message_details = "Shocking details."
    sql = "SELECT * FROM orders"
    query_result = {
        "status": "error",
        "data": {
            "errors": [{"message": message, "message_details": message_details}],
            "sql": sql,
        },
    }
    extracted = validator._extract_error_details(query_result)
    assert extracted["message"] == f"{message} {message_details}"
    assert extracted["sql"] == sql


def test_extract_error_details_error_list(validator):
    message = "An error message."
    query_result = {"status": "error", "data": [message]}
    extracted = validator._extract_error_details(query_result)
    assert extracted["message"] == message
    assert extracted["sql"] is None


def test_extract_error_details_error_other(validator):
    query_result = {"status": "error", "data": "some string"}
    with pytest.raises(TypeError):
        validator._extract_error_details(query_result)


def test_extract_error_details_error_non_str_message_details(validator):
    message = {"message": "An error messsage.", "details": "More details."}
    sql = "SELECT * FROM orders"
    query_result = {
        "status": "error",
        "data": {"errors": [{"message_details": message}], "sql": sql},
    }
    with pytest.raises(TypeError):
        validator._extract_error_details(query_result)


def test_extract_error_details_no_message_details(validator):
    message = "An error message."
    query_result = {
        "status": "error",
        "data": {"errors": [{"message": message, "message_details": None}]},
    }
    extracted = validator._extract_error_details(query_result)
    assert extracted["message"] == message
    assert extracted["sql"] is None


def test_extract_error_details_error_loc_wo_line(validator):
    message = "An error message."
    sql = "SELECT x FROM orders"
    query_result = {
        "status": "error",
        "data": {
            "errors": [{"message": message, "sql_error_loc": {"character": 8}}],
            "sql": sql,
        },
    }
    extracted = validator._extract_error_details(query_result)
    assert extracted["message"] == message
    assert extracted["sql"] == sql
