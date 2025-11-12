# Clean Up Images from Self-Hosted Docker Registries

If you're running a self-hosted Docker registry (using tools like [unregistry](https://github.com/psviderski/unregistry)), you'll want to clean up old images to reclaim disk space. This tool connects to your local Docker daemon and removes old images from specified repositories while keeping the ones you actually need.

The cleanup logic is simple: keep your N most recent images and anything built in the last M days. Everything else gets removed. Images currently in use by containers are automatically skipped.

This tool is designed for managing images from self-hosted registries and probably shouldn't be used for general local Docker cleanup.

## Installation

```bash
pip install docker-image-cleanup
```

Or using `uv`:

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

## Requirements

- Python 3.11+
- Docker daemon running locally
- Docker Python SDK

## Development

```bash
# Clone the repository
git clone https://github.com/iloveitaly/docker-image-cleanup
cd docker-image-cleanup

# Install dependencies
uv sync

# Run tests
pytest

# Run the CLI
uv run docker-image-cleanup --help
```

# [MIT License](LICENSE.md)
