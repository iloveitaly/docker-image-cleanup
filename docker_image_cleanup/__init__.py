import click
import docker
import docker.errors
import structlog
from collections import defaultdict
from whenever import Instant
from structlog_config import configure_logger

configure_logger()
log = structlog.get_logger()


def human_size(size_bytes):
    size = size_bytes
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def clean_repo(client, image_repo, num_recent, min_age_days, dry_run, now):
    images = client.images.list(name=image_repo)
    if not images:
        log.info("no images", repo=image_repo)
        return 0

    sorted_images = sorted(
        images, key=lambda img: Instant.parse_iso(img.attrs["Created"]), reverse=True
    )

    keep_tags = set()
    for img in sorted_images[:num_recent]:
        keep_tags.update(img.tags)

    min_age = now.subtract(hours=min_age_days * 24)
    for img in images:
        created = Instant.parse_iso(img.attrs["Created"])
        log.debug("inspecting image", image_id=img.id, tags=img.tags, created=created)
        if created >= min_age:
            keep_tags.update(img.tags)

    tags_to_remove = []
    for img in images:
        for tag in img.tags:
            if tag not in keep_tags and tag.startswith(image_repo + ":"):
                tags_to_remove.append((tag, img))

    remove_by_id = defaultdict(list)
    for tag, img in tags_to_remove:
        remove_by_id[img.id].append(tag)

    total_saved = 0
    for img_id, remove_tags in remove_by_id.items():
        img = client.images.get(img_id)
        all_tags = img.tags
        if set(remove_tags) == set(all_tags):
            in_use = (
                len(client.containers.list(all=True, filters={"ancestor": img_id})) > 0
            )
            if in_use:
                log.warning("skipped image in use", image_id=img_id, tags=remove_tags)
                continue
            size = img.attrs.get("Size", 0)
            if dry_run:
                log.info(
                    "would remove image",
                    image_id=img_id,
                    tags=remove_tags,
                    size=human_size(size),
                )
            else:
                for tag in remove_tags:
                    client.images.remove(tag, force=False)
                log.info(
                    "removed image",
                    image_id=img_id,
                    tags=remove_tags,
                    size=human_size(size),
                )
            total_saved += size
        else:
            if dry_run:
                log.info("would untag", tags=remove_tags)
            else:
                for tag in remove_tags:
                    try:
                        client.images.remove(tag, force=False)
                        log.info("untagged", tag=tag)
                    except docker.errors.APIError as e:
                        log.warning("skipped untag", tag=tag, reason=str(e))

    msg = "total space that would be saved" if dry_run else "total space saved"
    log.info(msg, bytes=total_saved, human=human_size(total_saved))
    return total_saved


@click.command()
@click.argument("image_repos", nargs=-1, required=True)
@click.option(
    "--num-recent", default=5, help="Number of recent tags to keep.", show_default=True
)
@click.option(
    "--min-age-days",
    default=30,
    help="Minimum age in days to keep tags.",
    show_default=True,
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate removal without executing.",
    show_default=True,
)
def main(image_repos, num_recent, min_age_days, dry_run):
    client = docker.from_env()
    now = Instant.now()

    grand_total = 0
    for image_repo in image_repos:
        log.info("cleaning repo", repo=image_repo)
        grand_total += clean_repo(
            client, image_repo, num_recent, min_age_days, dry_run, now
        )

    if len(image_repos) > 1:
        msg = (
            "grand total space that would be saved"
            if dry_run
            else "grand total space saved"
        )
        log.info(msg, bytes=grand_total, human=human_size(grand_total))
