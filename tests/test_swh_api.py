import pytest
from unittest.mock import patch, MagicMock
from swh_api import fetch_directory_hash_for_revision, verify_directory


class TestFetchDirectoryHashForRevision:
    def test_returns_directory_hash_on_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"directory": "abc123def456"}
        with patch("swh_api.requests.get", return_value=mock_resp):
            result = fetch_directory_hash_for_revision("deadbeef" * 5)
        assert result == "abc123def456"

    def test_returns_none_on_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("swh_api.requests.get", return_value=mock_resp):
            result = fetch_directory_hash_for_revision("deadbeef" * 5)
        assert result is None

    def test_raises_on_rate_limit(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        with patch("swh_api.requests.get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="rate limit"):
                fetch_directory_hash_for_revision("deadbeef" * 5)

    def test_raises_on_other_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")
        with patch("swh_api.requests.get", return_value=mock_resp):
            with pytest.raises(Exception):
                fetch_directory_hash_for_revision("deadbeef" * 5)


class TestVerifyDirectory:
    def test_returns_true_when_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("swh_api.requests.get", return_value=mock_resp):
            assert verify_directory("somehash") is True

    def test_returns_false_when_not_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("swh_api.requests.get", return_value=mock_resp):
            assert verify_directory("unknownhash") is False
