# Docker Image Cleanup

Clean up old Docker images from your local Docker image store while preserving recent images and those meeting age requirements.

## Features

- Remove old Docker images based on age and recency criteria
- Keep a configurable number of recent images
- Preserve images newer than a specified age threshold
- Skip images currently in use by containers
- Dry-run mode to preview changes before execution
- Human-readable disk space savings reporting
- Structured logging for detailed operation visibility

## Installation

```bash
pip install docker-image-cleanup
```

Or using `uv`:

```bash
uv tool install docker-image-cleanup
```

## Usage

```bash
# Basic usage - clean a single repository
docker-image-cleanup myrepo/myimage

# Clean multiple repositories
docker-image-cleanup myrepo/image1 myrepo/image2

# Dry run to see what would be removed
docker-image-cleanup --dry-run myrepo/myimage

# Keep 3 most recent images (default: 5)
docker-image-cleanup --num-recent 3 myrepo/myimage

# Keep images from last 7 days (default: 30)
docker-image-cleanup --min-age-days 7 myrepo/myimage

# Combine options
docker-image-cleanup --num-recent 3 --min-age-days 7 --dry-run myrepo/myimage
```

## How It Works

The cleanup process:

1. Lists all images for the specified repository
2. Identifies images to keep based on:
   - The N most recently created images (--num-recent)
   - Images created within the last M days (--min-age-days)
3. Removes or untags images not meeting retention criteria
4. Skips images currently in use by containers
5. Reports total disk space saved

## Options

- `--num-recent`: Number of recent images to keep (default: 5)
- `--min-age-days`: Minimum age in days to keep images (default: 30)
- `--dry-run`: Preview what would be removed without making changes

## Requirements

- Python 3.10+
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

## License

MIT
