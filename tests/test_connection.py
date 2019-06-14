import pytest
import requests
import requests_mock
from tests.mock import looker_mock
from fonz import connection
from fonz.exceptions import SqlError, ConnectionError, FonzException

base = "https://test.looker.com"

client = connection.Fonz(
    url=base,
    client_id="CLIENT_ID",
    client_secret="CLIENT_SECRET",
    port=19999,
    api="3.0",
    project="test_project",
    branch="test_branch",
)


def test_connect_correct_credentials():

    with looker_mock as m:
        client.connect()
        assert client.session.headers == {"Authorization": "token FAKE_ACCESS_TOKEN"}


def test_connect_incorrect_credentials():

    client = connection.Fonz(
        url=base,
        client_id="CLIENT_ID",
        client_secret="WRONG_CLIENT_SECRET",
        port=19999,
        api="3.0",
        project="test_project",
    )

    with looker_mock as m:
        with pytest.raises(ConnectionError):
            client.connect()


def test_update_session():

    with looker_mock as m:
        client.update_session()


def test_get_explores():

    output = [
        {"model": "model_one", "explore": "explore_one"},
        {"model": "model_one", "explore": "explore_two"},
    ]

    with looker_mock as m:
        response = client.get_explores()
        assert response == output


def test_get_dimensions():

    output = ["dimension_one", "dimension_two"]

    with looker_mock as m:
        response = client.get_dimensions("model_one", "explore_one")
        assert response == output


def test_create_query():

    with looker_mock as m:
        client.create_query(
            model="model_one",
            explore_name="explore_one",
            dimensions=["dimension_one", "dimension_two"],
        )


def test_create_query_incorrect_explore():

    with looker_mock as m:
        with pytest.raises(FonzException):
            client.create_query(
                model="model_one",
                explore_name="explore_five",
                dimensions=["dimension_one", "dimension_two"],
            )


def test_run_query_one_row_returned():

    with looker_mock as m:
        response = client.run_query(1)
        assert response == [{"column_one": 123}]


def test_run_query_zero_rows_returned():

    with looker_mock as m:
        response = client.run_query(3)
        assert response == []


def test_validate_explore_one_row_pass():

    with looker_mock as m:
        client.validate_explore(
            "model_one", "explore_one", ["dimension_one", "dimension_two"]
        )


def test_validate_explore_zero_row_pass():

    with looker_mock as m:
        client.validate_explore(
            "model_two", "explore_three", ["dimension_one", "dimension_two"]
        )


def test_validate_explore_looker_error():

    with looker_mock as m:
        with pytest.raises(SqlError):
            client.validate_explore(
                "model_two", "explore_four", ["dimension_three", "dimension_four"]
            )
