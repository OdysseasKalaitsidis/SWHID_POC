# SPDX-FileCopyrightText: 2026 Odysseas Kalaitsidis
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock, patch
import requests
from swhid_tool.core import (
    compute_content_swhid,
    compute_directory_swhid,
    SWHClient
)

def test_compute_content_swhid():
    content = b"hello world\n"
    swhid = compute_content_swhid(content)
    assert swhid.startswith("swh:1:cnt:")
    # The SHA-1 hash part should be 40 chars
    hash_part = swhid.split(":")[-1]
    assert len(hash_part) == 40

def test_compute_directory_swhid():
    files = {
        "file1.txt": b"content 1",
        "file2.txt": b"content 2"
    }
    swhid = compute_directory_swhid(files)
    assert swhid.startswith("swh:1:dir:")
    hash_part = swhid.split(":")[-1]
    assert len(hash_part) == 40

def test_swh_client_initialization():
    client_no_auth = SWHClient()
    assert "Authorization" not in client_no_auth.session.headers
    assert "User-Agent" in client_no_auth.session.headers

    client_with_auth = SWHClient(auth_token="dummy_token")
    assert client_with_auth.session.headers["Authorization"] == "Bearer dummy_token"
    assert "User-Agent" in client_with_auth.session.headers

@patch("requests.Session.get")
def test_swh_client_check_swhid(mock_get):
    client = SWHClient()
    
    # Mocking 200 OK
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    
    dummy_swhid = "swh:1:cnt:943a702d6893f0b2f4f2c00227d8196e85741639"
    assert client.check_swhid(dummy_swhid) is True
    mock_get.assert_called_with(
        "https://archive.softwareheritage.org/api/1/content/sha1_git:943a702d6893f0b2f4f2c00227d8196e85741639/",
        timeout=30
    )

    # Mocking 404
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp
    assert client.check_swhid(dummy_swhid) is False

    # Mocking exception
    mock_get.side_effect = requests.exceptions.RequestException("API down")
    assert client.check_swhid(dummy_swhid) is False
