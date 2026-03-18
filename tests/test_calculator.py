import os
import io
import tarfile
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from calculator import find_source, strip_cargo_injected_files, swhid_generator, CARGO_INJECTED


def make_tarball(files: dict) -> bytes:
    """Build an in-memory .tar.gz from a dict of {path: content_bytes}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, content in files.items():
            info = tarfile.TarInfo(name=path)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


class TestFindSource:
    def test_unwraps_single_top_level_dir(self, tmp_path):
        inner = tmp_path / "mypackage-1.0"
        inner.mkdir()
        (inner / "setup.py").write_text("x")
        result = find_source(str(tmp_path))
        assert result == str(inner)

    def test_returns_extract_path_for_multiple_items(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        result = find_source(str(tmp_path))
        assert result == str(tmp_path)

    def test_returns_extract_path_when_single_item_is_file(self, tmp_path):
        (tmp_path / "README.md").write_text("hello")
        result = find_source(str(tmp_path))
        assert result == str(tmp_path)


class TestStripCargoInjectedFiles:
    def test_removes_known_injected_files(self, tmp_path):
        for f in CARGO_INJECTED:
            (tmp_path / f).write_text("data")
        removed = strip_cargo_injected_files(str(tmp_path))
        assert set(removed) == set(CARGO_INJECTED)
        for f in CARGO_INJECTED:
            assert not (tmp_path / f).exists()

    def test_returns_only_existing_files(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("data")
        removed = strip_cargo_injected_files(str(tmp_path))
        assert removed == ["Cargo.toml"]

    def test_returns_empty_list_when_nothing_to_remove(self, tmp_path):
        removed = strip_cargo_injected_files(str(tmp_path))
        assert removed == []


class TestSwhidGenerator:
    def test_returns_swhid_string(self, tmp_path):
        (tmp_path / "hello.py").write_text("print('hello')")
        swhid = swhid_generator(str(tmp_path))
        swhid_str = str(swhid)
        assert swhid_str.startswith("swh:1:dir:")
        assert len(swhid_str.split(":")[-1]) == 40

    def test_different_contents_give_different_swhids(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "file.py").write_text("x = 1")
        (dir_b / "file.py").write_text("x = 2")
        assert str(swhid_generator(str(dir_a))) != str(swhid_generator(str(dir_b)))

    def test_same_contents_give_same_swhid(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "file.py").write_text("x = 1")
        (dir_b / "file.py").write_text("x = 1")
        assert str(swhid_generator(str(dir_a))) == str(swhid_generator(str(dir_b)))
