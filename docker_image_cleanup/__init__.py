"""
Cleans up old Docker images from local storage with retention controls.
"""

from collections import defaultdict
from typing import Any

import click
import docker
import docker.errors
from pydantic import BaseModel, Field
from structlog_config import configure_logger
from whenever import Instant

log = configure_logger()


class CleanupConfig(BaseModel):
    """Configuration for cleaning up Docker images."""

    num_recent: int = Field(5, description="Number of recent tags to keep.")
    min_age_days: int = Field(30, description="Minimum age in days to keep tags.")
    dry_run: bool = Field(False, description="Simulate removal without executing.")


class ImageInfo(BaseModel):
    """Abstract representation of a Docker image for logic processing."""

    id: str
    tags: list[str]
    created: Instant
    size: int
    is_in_use: bool = False


def format_size(size_bytes: int) -> str:
    """Converts bytes to a human-readable string (KB, MB, GB, etc.)."""
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def parse_docker_image(
    image_data: Any, used_image_ids: set[str] # Use Any due to pyright resolution issues with docker library types
) -> ImageInfo:
    """Parses docker.models.images.Image into our ImageInfo model."""
    created_instant = Instant.parse_iso(image_data.attrs["Created"])
    image_id = image_data.id

    return ImageInfo(
        id=image_id,
        tags=image_data.tags or [],
        created=created_instant,
        size=image_data.attrs.get("Size", 0),
        is_in_use=image_id in used_image_ids,
    )


def get_images_to_process(
    client: docker.DockerClient, repo_name: str, used_image_ids: set[str]
) -> list[ImageInfo]:
    """Fetches and parses Docker images for a given repository."""
    images = client.images.list(name=repo_name)
    if not images:
        log.info("no images found for repository", repo=repo_name)
        return []

    parsed_images = [parse_docker_image(img, used_image_ids) for img in images]
    return sorted(parsed_images, key=lambda img: img.created, reverse=True)


def determine_cleanup_actions(
    images: list[ImageInfo], config: CleanupConfig, now: Instant, repo_name: str
) -> dict[str, Any]:
    """Determines which images/tags to remove based on criteria."""
    if not images:
        return {"images_to_delete": [], "tags_to_remove": [], "total_size_saved": 0}

    keep_tags: set[str] = set()
    for img in images[: config.num_recent]:
        keep_tags.update(img.tags)

    min_age_threshold = now.subtract(hours=config.min_age_days * 24)
    for img in images:
        if img.created >= min_age_threshold:
            keep_tags.update(img.tags)

    images_to_delete_ids: set[str] = set()
    tags_to_remove: list[str] = []

    images_by_id: dict[str, list[ImageInfo]] = defaultdict(list)
    for img in images:
        images_by_id[img.id].append(img)

    total_size_saved = 0
    repo_prefix = repo_name + ":"

    for img_id, img_list in images_by_id.items():
        all_image_tags = set()
        for img in img_list:
            all_image_tags.update(img.tags)

        current_image_repo_tags = {
            tag for tag in all_image_tags if tag.startswith(repo_prefix)
        }

        tags_for_this_image_to_remove = [
            tag for tag in current_image_repo_tags if tag not in keep_tags
        ]

        if tags_for_this_image_to_remove:
            tags_to_remove.extend(tags_for_this_image_to_remove)

            if set(tags_for_this_image_to_remove) == current_image_repo_tags:
                img_info = img_list[0]
                if not img_info.is_in_use:
                    images_to_delete_ids.add(img_id)
                    total_size_saved += img_info.size
                else:
                    log.warning(
                        "skipped image in use",
                        image_id=img_id,
                        tags=tags_for_this_image_to_remove,
                    )

    return {
        "images_to_delete": list(images_to_delete_ids),
        "tags_to_remove": list(set(tags_to_remove)),
        "total_size_saved": total_size_saved,
    }


def execute_cleanup(
    client: docker.DockerClient,
    images_to_delete: list[str],
    tags_to_remove: list[str],
    total_size_saved: int,
    dry_run: bool,
) -> int:
    """Executes the determined cleanup actions."""
    executed_size_saved = 0

    if dry_run:
        if tags_to_remove:
            log.info("would remove tags", tags=tags_to_remove)
        if images_to_delete:
            log.info("would remove images", image_ids=images_to_delete)

        log.info(
            "total space that would be saved",
            bytes=total_size_saved,
            human=format_size(total_size_saved),
        )
        return total_size_saved

    for tag in tags_to_remove:
        try:
            client.images.remove(tag, force=False)
            log.info("untagged image", tag=tag)
        except docker.errors.APIError as e:
            log.warning("skipped untagging", tag=tag, reason=str(e))

    for img_id in images_to_delete:
        try:
            img = client.images.get(img_id)
            size = img.attrs.get("Size", 0)
            client.images.remove(img_id, force=False)
            log.info("removed image", image_id=img_id, size=format_size(size))
            executed_size_saved += size
        except docker.errors.ImageNotFound:
            log.warning("image already removed", image_id=img_id)
        except docker.errors.APIError as e:
            log.warning("skipped image removal", image_id=img_id, reason=str(e))

    log.info(
        "total space saved",
        bytes=executed_size_saved,
        human=format_size(executed_size_saved),
    )
    return executed_size_saved


@click.command()
@click.argument("image_repos", nargs=-1, required=True)
@click.option(
    "--num-recent",
    default=5,
    type=int,
    help="Number of recent tags to keep.",
    show_default=True,
)
@click.option(
    "--min-age-days",
    default=30,
    type=int,
    help="Minimum age in days to keep tags.",
    show_default=True,
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Simulate removal without executing.",
    show_default=True,
)
def main(
    image_repos: tuple[str, ...], num_recent: int, min_age_days: int, dry_run: bool
):
    """
    Cleans up old Docker images from local storage with retention controls.

    IMAGE_REPOS are the repository names to clean (e.g., 'my/app', 'ubuntu').
    """
    try:
        client = docker.from_env()
        now = Instant.now()

        try:
            all_containers = client.containers.list(all=True)
            used_image_ids: set[str] = {
                container.image.id
                for container in all_containers
                if container.image and container.image.id
            }
            log.debug("determined used image IDs", count=len(used_image_ids))
        except docker.errors.APIError as e:
            log.error(
                "failed to list containers, cannot determine in-use images",
                reason=str(e),
            )
            used_image_ids = set()

        config = CleanupConfig(
            num_recent=num_recent,
            min_age_days=min_age_days,
            dry_run=dry_run,
        )

        grand_total_saved = 0
        for repo_name in image_repos:
            log.info("processing repository", repo=repo_name)

            images = get_images_to_process(client, repo_name, used_image_ids)

            if not images:
                continue

            actions = determine_cleanup_actions(images, config, now, repo_name)

            executed_bytes_saved = execute_cleanup(
                client=client,
                images_to_delete=actions["images_to_delete"],
                tags_to_remove=actions["tags_to_remove"],
                total_size_saved=actions["total_size_saved"],
                dry_run=config.dry_run,
            )
            grand_total_saved += executed_bytes_saved

        if len(image_repos) > 1:
            result_msg = (
                "grand total space that would be saved"
                if dry_run
                else "grand total space saved"
            )
            log.info(
                result_msg,
                bytes=grand_total_saved,
                human=format_size(grand_total_saved),
            )

    except docker.errors.DockerException as e:
        log.error("failed to connect to Docker daemon", reason=str(e))
        exit(1)
    except Exception:
        log.exception("an unexpected error occurred")
        exit(1)


if __name__ == "__main__":
    main()
