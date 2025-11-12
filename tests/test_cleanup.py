"""Test docker image cleanup functionality."""

from unittest.mock import Mock
from whenever import Instant

from docker_image_cleanup import human_size, clean_repo


def test_human_size():
    assert human_size(0) == "0.00 B"
    assert human_size(512) == "512.00 B"
    assert human_size(1024) == "1.00 KB"
    assert human_size(1024 * 1024) == "1.00 MB"
    assert human_size(1024 * 1024 * 1024) == "1.00 GB"
    assert human_size(1024 * 1024 * 1024 * 1024) == "1.00 TB"
    assert human_size(1536) == "1.50 KB"


def test_clean_repo_no_images():
    client = Mock()
    client.images.list.return_value = []
    now = Instant.now()

    result = clean_repo(client, "test/repo", 5, 30, True, now)

    assert result == 0
    client.images.list.assert_called_once_with(name="test/repo")


def test_clean_repo_keeps_recent_images():
    client = Mock()
    now = Instant.now()

    recent_img = Mock()
    recent_img.id = "img1"
    recent_img.tags = ["test/repo:latest"]
    recent_img.attrs = {"Created": now.format_iso(), "Size": 1000000}

    client.images.list.return_value = [recent_img]

    result = clean_repo(client, "test/repo", 5, 30, True, now)

    assert result == 0
    client.images.remove.assert_not_called()


def test_clean_repo_removes_old_images():
    client = Mock()
    now = Instant.now()
    old_date = now.subtract(hours=60 * 24)

    old_img = Mock()
    old_img.id = "img1"
    old_img.tags = ["test/repo:old"]
    old_img.attrs = {"Created": old_date.format_iso(), "Size": 1000000}

    client.images.list.return_value = [old_img]
    client.images.get.return_value = old_img
    client.containers.list.return_value = []

    result = clean_repo(client, "test/repo", 0, 30, True, now)

    assert result == 1000000
    client.images.remove.assert_not_called()


def test_clean_repo_skips_images_in_use():
    client = Mock()
    now = Instant.now()
    old_date = now.subtract(hours=60 * 24)

    old_img = Mock()
    old_img.id = "img1"
    old_img.tags = ["test/repo:old"]
    old_img.attrs = {"Created": old_date.format_iso(), "Size": 1000000}

    container = Mock()

    client.images.list.return_value = [old_img]
    client.images.get.return_value = old_img
    client.containers.list.return_value = [container]

    result = clean_repo(client, "test/repo", 0, 30, True, now)

    assert result == 0
    client.images.remove.assert_not_called()


def test_clean_repo_dry_run_false():
    client = Mock()
    now = Instant.now()
    old_date = now.subtract(hours=60 * 24)

    old_img = Mock()
    old_img.id = "img1"
    old_img.tags = ["test/repo:old"]
    old_img.attrs = {"Created": old_date.format_iso(), "Size": 1000000}

    client.images.list.return_value = [old_img]
    client.images.get.return_value = old_img
    client.containers.list.return_value = []

    result = clean_repo(client, "test/repo", 0, 30, False, now)

    assert result == 1000000
    client.images.remove.assert_called_once_with("test/repo:old", force=False)
