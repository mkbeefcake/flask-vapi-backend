import pytest
from flask import Flask
from aldershot import asbp

@pytest.fixture
def app():
    """Create application for the tests."""
    app = Flask(__name__)
    app.register_blueprint(asbp)
    return app

@pytest.fixture
def client(app):
    """Create test client for the tests."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create test CLI runner for the tests."""
    return app.test_cli_runner()