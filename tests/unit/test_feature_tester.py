"""
Unit tests for agents/feature_tester/worker.py.
"""

import pytest
import warnings
from unittest.mock import patch, MagicMock

from agents.feature_tester.worker import (
    FeatureTesterWorker,
    _pending_credentials,
)


@pytest.fixture(autouse=True)
def clear_pending_credentials():
    """Clear the module-level pending credentials dict before each test."""
    _pending_credentials.clear()
    yield
    _pending_credentials.clear()


@pytest.fixture
def mock_vault():
    return MagicMock()


@pytest.fixture
def worker(mock_vault):
    with patch("agents.feature_tester.worker.get_vault", return_value=mock_vault):
        w = FeatureTesterWorker("test-agent-001", "memory/test.md")
    return w


@pytest.mark.unit
class TestFeatureTesterWorkerCredentials:
    """Tests for the side-channel credential mechanism."""

    def test_credentials_from_side_channel(self, worker):
        """Pending creds used when objective has none."""
        FeatureTesterWorker.set_pending_credentials(
            "test-agent-001", "foo", "bar"
        )
        creds = worker._get_pending_credentials()
        assert creds == {"username": "foo", "password": "bar"}

    def test_objective_creds_ignored(self, worker):
        """When both present, pending wins."""
        worker.objective = "Test login with username=old_user and password=old_pass"
        FeatureTesterWorker.set_pending_credentials(
            "test-agent-001", "new_user", "new_pass"
        )
        creds = worker._get_pending_credentials()
        assert creds == {"username": "new_user", "password": "new_pass"}

    def test_pending_creds_consumed(self, worker):
        """Second call returns None."""
        FeatureTesterWorker.set_pending_credentials(
            "test-agent-001", "foo", "bar"
        )
        first = worker._get_pending_credentials()
        assert first == {"username": "foo", "password": "bar"}

        second = worker._get_pending_credentials()
        assert second is None

    def test_parse_credentials_deprecated(self, worker):
        """Old method returns None + warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = worker._parse_credentials()

        assert result is None
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "_parse_credentials is deprecated" in str(w[0].message)
