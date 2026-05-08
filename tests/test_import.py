"""Test docker-image-cleanup."""

import docker_image_cleanup


def test_import() -> None:
    """Test that the  can be imported."""
    assert isinstance(docker_image_cleanup.__name__, str)


def test_version() -> None:
    """Test that the version is available."""
    assert isinstance(docker_image_cleanup.__version__, str)
