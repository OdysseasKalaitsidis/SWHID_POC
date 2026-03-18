import pytest
from unittest.mock import patch, MagicMock
from parser import fetch_package, fetch_crate, list_wheels


MOCK_PYPI_RESPONSE = {
    "urls": [
        {
            "packagetype": "sdist",
            "url": "https://files.pythonhosted.org/packages/six-1.17.0.tar.gz",
            "filename": "six-1.17.0.tar.gz",
            "size": 12345,
        },
        {
            "packagetype": "bdist_wheel",
            "url": "https://files.pythonhosted.org/packages/six-1.17.0-py3-none-any.whl",
            "filename": "six-1.17.0-py3-none-any.whl",
            "size": 9876,
        },
    ]
}

MOCK_PYPI_WHEELS_ONLY = {
    "urls": [
        {
            "packagetype": "bdist_wheel",
            "url": "https://files.pythonhosted.org/packages/pkg-1.0-cp39-cp39-linux_x86_64.whl",
            "filename": "pkg-1.0-cp39-cp39-linux_x86_64.whl",
            "size": 5000,
        }
    ]
}

MOCK_CRATE_RESPONSE = {
    "version": {
        "yanked": False,
        "num": "1.0.203",
    }
}

MOCK_YANKED_CRATE_RESPONSE = {
    "version": {
        "yanked": True,
        "num": "0.1.0",
    }
}


class TestFetchPackage:
    def test_returns_sdist_url(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_PYPI_RESPONSE
        with patch("parser.requests.get", return_value=mock_resp):
            url = fetch_package("six", "1.17.0")
        assert url == "https://files.pythonhosted.org/packages/six-1.17.0.tar.gz"

    def test_raises_when_no_sdist(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_PYPI_WHEELS_ONLY
        with patch("parser.requests.get", return_value=mock_resp):
            with pytest.raises(ValueError, match="No sdist found"):
                fetch_package("pkg", "1.0")

    def test_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        with patch("parser.requests.get", return_value=mock_resp):
            with pytest.raises(Exception):
                fetch_package("nonexistent", "0.0.0")


class TestFetchCrate:
    def test_returns_download_url(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_CRATE_RESPONSE
        with patch("parser.requests.get", return_value=mock_resp):
            url = fetch_crate("serde", "1.0.203")
        assert url == "https://static.crates.io/crates/serde/serde-1.0.203.crate"

    def test_raises_for_yanked_crate(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_YANKED_CRATE_RESPONSE
        with patch("parser.requests.get", return_value=mock_resp):
            with pytest.raises(ValueError, match="yanked"):
                fetch_crate("oldcrate", "0.1.0")


class TestListWheels:
    def test_returns_wheel_metadata(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_PYPI_RESPONSE
        with patch("parser.requests.get", return_value=mock_resp):
            wheels = list_wheels("six", "1.17.0")
        assert len(wheels) == 1
        w = wheels[0]
        assert w["filename"] == "six-1.17.0-py3-none-any.whl"
        assert w["python"] == "py3"
        assert w["abi"] == "none"
        assert w["platform"] == "any"

    def test_returns_empty_list_when_no_wheels(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "urls": [{"packagetype": "sdist", "url": "x", "filename": "x.tar.gz", "size": 1}]
        }
        with patch("parser.requests.get", return_value=mock_resp):
            wheels = list_wheels("pkg", "1.0")
        assert wheels == []
