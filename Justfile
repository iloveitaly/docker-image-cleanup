# Set up the Python environment, done automatically for you when using direnv
setup:
    uv venv && uv sync
    @echo "activate: source ./.venv/bin/activate"

# Start docker services
up:
    docker compose up -d --wait

# Run tests
test:
    uv run pytest -v

# Run linting checks
lint FILES=".":
    #!/usr/bin/env bash
    set +e
    exit_code=0
    
    if [ -n "${CI:-}" ]; then
        # CI mode: GitHub-friendly output
        uv run ruff check --output-format=github {{FILES}} || exit_code=$?
        uv run ruff format --check {{FILES}} || exit_code=$?
        
        uv run pyright {{FILES}} --outputjson > pyright_report.json || exit_code=$?
        jq -r \
            --arg root "$GITHUB_WORKSPACE/" \
            '
                .generalDiagnostics[] |
                .file as $file |
                ($file | sub("^\\Q\($root)\\E"; "")) as $rel_file |
                "::\(.severity) file=\($rel_file),line=\(.range.start.line),endLine=\(.range.end.line),col=\(.range.start.character),endColumn=\(.range.end.character)::\($rel_file):\(.range.start.line): \(.message)"
            ' < pyright_report.json
        rm pyright_report.json
    else
        # Local mode: regular output
        uv run ruff check {{FILES}} || exit_code=$?
        uv run ruff format --check {{FILES}} || exit_code=$?
        uv run pyright {{FILES}} || exit_code=$?
    fi
    
    if [ $exit_code -ne 0 ]; then
        echo "One or more linting checks failed"
        exit 1
    fi

# Automatically fix linting errors
lint-fix:
    uv run ruff check . --fix
    uv run ruff format .

# Clean build artifacts and cache
clean:
    rm -rf *.egg-info .venv
    find . -type d -name "__pycache__" -prune -exec rm -rf {} \; 2>/dev/null || true

# Update copier template
update_copier:
    uv tool run --with jinja2_shell_extension \
        copier@latest update --vcs-ref=HEAD --trust --skip-tasks --skip-answered
