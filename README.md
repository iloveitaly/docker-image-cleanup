# Clean Up Images from Self-Hosted Docker Registries

If you're running a self-hosted Docker registry (using tools like [unregistry](https://github.com/psviderski/unregistry)), you'll want to clean up old images to reclaim disk space. This tool connects to your local Docker daemon and removes old images from specified repositories while keeping the ones you actually need.

The cleanup logic is simple: keep your N most recent images and anything built in the last M days. Everything else gets removed. Images currently in use by containers are automatically skipped.

This tool is designed for managing images from self-hosted registries and probably shouldn't be used for general local Docker cleanup.

## Installation

```bash
uv tool install docker-image-cleanup
```

## Usage

The basic command takes one or more image repositories:

```bash
docker-image-cleanup myrepo/myimage
```

You can clean multiple repositories at once:

```bash
docker-image-cleanup myrepo/image1 myrepo/image2
```

Before running the cleanup for real, use `--dry-run` to see what would be removed:

```bash
docker-image-cleanup --dry-run myrepo/myimage
```

Adjust the retention policy with `--num-recent` and `--min-age-days`:

```bash
# Keep only the 3 most recent images
docker-image-cleanup --num-recent 3 myrepo/myimage

# Keep images from the last 7 days
docker-image-cleanup --min-age-days 7 myrepo/myimage

# Combine both options
docker-image-cleanup --num-recent 3 --min-age-days 7 myrepo/myimage
```

## Docker

This tool is available as a Docker image on GHCR. It's designed to run on a schedule using a built-in cron system.

### Environment Variables

- `TARGET_REPOS`: A space-separated list of image repositories to clean (e.g., `myrepo/image1 myrepo/image2`). **Required**.
- `SCHEDULE`: A cron expression for the cleanup schedule (default: `0 0 * * *` - daily at midnight).
- `NUM_RECENT`: Number of recent tags to keep (default: `5`).
- `MIN_AGE_DAYS`: Minimum age in days to keep tags (default: `30`).

### Docker Run

You must mount the Docker socket so the container can interact with your local Docker daemon:

```bash
docker run -d \
  --name docker-image-cleanup \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e TARGET_REPOS="myrepo/image1 myrepo/image2" \
  ghcr.io/iloveitaly/docker-image-cleanup:latest
```

### Docker Compose

```yaml
services:
  cleanup:
    image: ghcr.io/iloveitaly/docker-image-cleanup:latest
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - TARGET_REPOS=myrepo/image1 myrepo/image2
      - SCHEDULE=0 0 * * *
      - NUM_RECENT=5
      - MIN_AGE_DAYS=30
```

## Features

- Removes old Docker images based on age and recency criteria
- Keeps a configurable number of recent images (default: 5)
- Preserves images newer than a specified age threshold (default: 30 days)
- Automatically skips images currently in use by containers
- Dry-run mode to preview changes before execution
- Human-readable disk space savings reporting
- Structured logging for detailed operation visibility

## How It Works

The cleanup process is straightforward:

1. Lists all images for the specified repository
2. Identifies images to keep based on retention criteria (most recent N images and images newer than M days)
3. Removes or untags images that don't meet retention criteria
4. Skips any images currently in use by containers
5. Reports total disk space saved

Images with multiple tags are handled intelligently. If all tags on an image would be removed, the entire image is deleted. If only some tags would be removed, those tags are untagged but the image remains.

# [MIT License](LICENSE.md)
