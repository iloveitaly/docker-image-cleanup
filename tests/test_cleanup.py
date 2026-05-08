"""Test docker image cleanup functionality."""

from unittest.mock import Mock

import docker.errors
from docker.models.images import Image
from whenever import Instant

from docker_image_cleanup import (
    CleanupConfig,
    ImageInfo,
    determine_cleanup_actions,
    execute_cleanup,
    format_size,
    get_images_to_process,
    parse_docker_image,
)


def test_format_size():
    """Tests the human-readable size formatting."""
    assert format_size(0) == "0.00 B"
    assert format_size(512) == "512.00 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1024 * 1024) == "1.00 MB"
    assert format_size(1024 * 1024 * 1024) == "1.00 GB"
    assert format_size(1024 * 1024 * 1024 * 1024) == "1.00 TB"
    assert format_size(1536) == "1.50 KB"


def test_get_images_to_process_empty():
    """Tests get_images_to_process when no images are found."""
    client = Mock()
    client.images.list.return_value = []
    used_image_ids = set()

    images = get_images_to_process(client, "test/repo", used_image_ids)

    assert images == []
    client.images.list.assert_called_once_with(name="test/repo")


def test_get_images_to_process_parses_correctly():
    """Tests that images are parsed into ImageInfo correctly."""
    client = Mock()
    now = Instant.now()

    mock_image_1 = Mock(spec=Image)
    mock_image_1.id = "sha256:img1"
    mock_image_1.tags = ["test/repo:latest", "test/repo:v1.0"]
    mock_image_1.attrs = {"Created": now.format_iso(), "Size": 1000000}

    mock_image_2 = Mock(spec=Image)
    mock_image_2.id = "sha256:img2"
    mock_image_2.tags = ["test/repo:dev"]
    mock_image_2.attrs = {
        "Created": (now.subtract(hours=24 * 10)).format_iso(),
        "Size": 500000,
    }

    client.images.list.return_value = [mock_image_1, mock_image_2]
    used_image_ids = {"sha256:img1"}

    images = get_images_to_process(client, "test/repo", used_image_ids)

    assert len(images) == 2
    assert images[0].id == "sha256:img1"
    assert images[1].id == "sha256:img2"
    assert images[0].tags == ["test/repo:latest", "test/repo:v1.0"]
    assert images[0].created == now
    assert images[0].size == 1000000
    assert images[0].is_in_use is True


def test_determine_cleanup_actions_keep_recent():
    """Tests that recent images are kept."""
    now = Instant.now()

    img1 = ImageInfo(
        id="img1", tags=["repo:latest"], created=now, size=100, is_in_use=False
    )
    img2 = ImageInfo(
        id="img2",
        tags=["repo:v2"],
        created=now.subtract(hours=2 * 24),
        size=200,
        is_in_use=False,
    )
    img3 = ImageInfo(
        id="img3",
        tags=["repo:v1"],
        created=now.subtract(hours=40 * 24),
        size=300,
        is_in_use=False,
    )

    images = [img1, img2, img3]
    config = CleanupConfig(num_recent=3, min_age_days=30)

    actions = determine_cleanup_actions(images, config, now, "repo")

    assert actions["images_to_delete"] == {}
    assert actions["tags_to_remove"] == []
    assert actions["total_size_saved"] == 0


def test_determine_cleanup_actions_keep_old_but_recent_enough():
    """Tests that images within min_age_days are kept, even if not in num_recent."""
    now = Instant.now()

    img1 = ImageInfo(
        id="img1", tags=["repo:latest"], created=now, size=100, is_in_use=False
    )
    img2 = ImageInfo(
        id="img2",
        tags=["repo:v2"],
        created=now.subtract(hours=2 * 24),
        size=200,
        is_in_use=False,
    )
    img3 = ImageInfo(
        id="img3",
        tags=["repo:v1"],
        created=now.subtract(hours=40 * 24),
        size=300,
        is_in_use=False,
    )

    images = [img1, img2, img3]
    config = CleanupConfig(num_recent=1, min_age_days=30)

    actions = determine_cleanup_actions(images, config, now, "repo")

    assert actions["images_to_delete"] == {"img3": 300}
    assert actions["tags_to_remove"] == ["repo:v1"]
    assert actions["total_size_saved"] == 300


def test_determine_cleanup_actions_remove_all_tags_but_in_use():
    """Tests that an image is not deleted if it's in use, even if all its tags are to be removed."""
    now = Instant.now()

    img1 = ImageInfo(
        id="img1",
        tags=["repo:latest", "repo:v1"],
        created=now.subtract(hours=50 * 24),
        size=500,
        is_in_use=True,
    )

    images = [img1]
    config = CleanupConfig(num_recent=0, min_age_days=0)

    actions = determine_cleanup_actions(images, config, now, "repo")

    assert actions["images_to_delete"] == {}
    assert set(actions["tags_to_remove"]) == {"repo:latest", "repo:v1"}
    assert actions["total_size_saved"] == 0


def test_determine_cleanup_actions_remove_multiple_images_and_tags():
    """Tests removal of multiple images and tags."""
    now = Instant.now()

    img1 = ImageInfo(
        id="img1", tags=["repo:latest"], created=now, size=100, is_in_use=True
    )
    img2 = ImageInfo(
        id="img2",
        tags=["repo:old-v1"],
        created=now.subtract(hours=60 * 24),
        size=200,
        is_in_use=False,
    )
    img3_tag1 = ImageInfo(
        id="img3",
        tags=["repo:old-v2a"],
        created=now.subtract(hours=60 * 24),
        size=300,
        is_in_use=False,
    )
    img3_tag2 = ImageInfo(
        id="img3",
        tags=["repo:keep-v2b"],
        created=now.subtract(hours=5 * 24),
        size=300,
        is_in_use=False,
    )

    images = [img1, img2, img3_tag1, img3_tag2]
    images.sort(key=lambda img: img.created, reverse=True)

    config = CleanupConfig(num_recent=1, min_age_days=30)

    actions = determine_cleanup_actions(images, config, now, "repo")

    assert "img2" in actions["images_to_delete"]
    assert len(actions["images_to_delete"]) == 1
    assert "repo:old-v1" in actions["tags_to_remove"]
    assert "repo:old-v2a" in actions["tags_to_remove"]
    assert len(actions["tags_to_remove"]) == 2
    assert actions["total_size_saved"] == 200


def test_execute_cleanup_dry_run():
    """Tests execute_cleanup in dry_run mode."""
    client = Mock()
    images_to_delete = {"img_to_delete_id": 500000}
    tags_to_remove = ["repo:old-tag"]
    total_size_saved = 500000

    result = execute_cleanup(
        client, images_to_delete, tags_to_remove, total_size_saved, dry_run=True
    )

    assert result == total_size_saved
    client.images.remove.assert_not_called()


def test_execute_cleanup_removes_tag_and_image():
    """Tests execute_cleanup when removing a tag and a full image."""
    client = Mock()
    now = Instant.now()

    img_to_delete = Mock(spec=Image)
    img_to_delete.id = "img_to_delete_id"
    img_to_delete.tags = ["repo:old-tag"]
    img_to_delete.attrs = {"Created": now.format_iso(), "Size": 500000}

    client.images.get.return_value = img_to_delete
    client.images.remove.return_value = None

    images_to_delete = {"img_to_delete_id": 500000}
    tags_to_remove = ["repo:old-tag"]
    total_size_saved = 500000

    result = execute_cleanup(
        client, images_to_delete, tags_to_remove, total_size_saved, dry_run=False
    )

    assert result == 500000
    client.images.remove.assert_any_call("repo:old-tag", force=False)
    client.images.remove.assert_any_call("img_to_delete_id", force=False)
    assert client.images.remove.call_count == 2


def test_execute_cleanup_skips_untagging_on_api_error():
    """Tests handling of API errors during untagging."""
    client = Mock()

    def remove_side_effect(tag_or_id, force=False):
        if tag_or_id == "repo:tag1":
            raise docker.errors.APIError("Simulated API error")
        return None

    client.images.remove.side_effect = remove_side_effect

    images_to_delete = {}
    tags_to_remove = ["repo:tag1", "repo:tag2"]
    total_size_saved = 0

    execute_cleanup(
        client, images_to_delete, tags_to_remove, total_size_saved, dry_run=False
    )

    client.images.remove.assert_any_call("repo:tag1", force=False)
    client.images.remove.assert_any_call("repo:tag2", force=False)
    assert client.images.remove.call_count == 2


def test_parse_docker_image_fallbacks():
    """Tests parse_docker_image with missing or invalid Created attribute."""
    # Case 1: Missing Created, has Metadata.LastTagTime
    mock_img = Mock(spec=Image)
    mock_img.id = "sha256:fallback"
    mock_img.tags = ["test:tag"]
    last_tag_time = "2023-01-01T12:00:00Z"
    mock_img.attrs = {
        "Metadata": {"LastTagTime": last_tag_time},
        "Size": 100,
    }

    info = parse_docker_image(mock_img, set())
    assert info is not None
    assert info.created == Instant.parse_iso(last_tag_time)

    # Case 2: Missing Created, Missing Metadata (or None), returns None
    mock_img.attrs = {"Size": 100}
    info = parse_docker_image(mock_img, set())
    assert info is None

    # Case 3: Created is "0001-01-01T00:00:00Z", returns None
    mock_img.attrs = {"Created": "0001-01-01T00:00:00Z", "Size": 100}
    info = parse_docker_image(mock_img, set())
    assert info is None


def test_get_images_to_process_filters_unparsable():
    """Tests that get_images_to_process filters out images with missing Created info."""
    client = Mock()
    now = Instant.now()

    # Image 1: Valid
    mock_img_1 = Mock(spec=Image)
    mock_img_1.id = "sha256:valid"
    mock_img_1.tags = ["repo:v1"]
    mock_img_1.attrs = {"Created": now.format_iso(), "Size": 100}

    # Image 2: Invalid (Missing Created and Metadata)
    mock_img_2 = Mock(spec=Image)
    mock_img_2.id = "sha256:invalid"
    mock_img_2.tags = ["repo:v2"]
    mock_img_2.attrs = {"Size": 200}

    client.images.list.return_value = [mock_img_1, mock_img_2]
    images = get_images_to_process(client, "repo", set())

    assert len(images) == 1
    assert images[0].id == "sha256:valid"


def test_execute_cleanup_handles_image_already_removed_by_untagging():
    """Tests that execute_cleanup counts size when ImageNotFound is raised (auto-deleted)."""
    client = Mock()

    def remove_side_effect(tag_or_id, force=False):
        if tag_or_id == "img_to_delete_id":
            raise docker.errors.ImageNotFound("Simulated ImageNotFound")
        return None

    client.images.remove.side_effect = remove_side_effect

    images_to_delete = {"img_to_delete_id": 1000}
    tags_to_remove = ["repo:old-tag"]
    total_size_saved = 1000

    result = execute_cleanup(
        client, images_to_delete, tags_to_remove, total_size_saved, dry_run=False
    )

    assert result == 1000
    client.images.remove.assert_any_call("repo:old-tag", force=False)
    client.images.remove.assert_any_call("img_to_delete_id", force=False)


def test_execute_cleanup_skips_image_removal_on_api_error():
    """Tests that execute_cleanup skips size counting when APIError is raised on image removal."""
    client = Mock()

    def remove_side_effect(tag_or_id, force=False):
        if tag_or_id == "img_to_delete_id":
            raise docker.errors.APIError("Simulated API error")
        return None

    client.images.remove.side_effect = remove_side_effect

    images_to_delete = {"img_to_delete_id": 1000}
    tags_to_remove = ["repo:old-tag"]
    total_size_saved = 1000

    result = execute_cleanup(
        client, images_to_delete, tags_to_remove, total_size_saved, dry_run=False
    )

    assert result == 0
    client.images.remove.assert_any_call("repo:old-tag", force=False)
    client.images.remove.assert_any_call("img_to_delete_id", force=False)
