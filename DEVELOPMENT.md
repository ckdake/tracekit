# Development

## Repository Structure

This is a monorepo containing the Python package, a web dashboard, and the static website.

```
tracekit/
├── .devcontainer/       # Development container configuration
├── .github/workflows/   # CI/CD pipelines
├── app/                 # Web dashboard (Flask)
├── tracekit/            # Python package source
│   ├── commands/        # CLI command implementations
│   └── providers/       # Activity provider integrations
├── tests/               # Python tests (mirrors package structure)
├── site/                # Static website source
│   ├── src/             # Website source files
│   ├── scripts/         # Build scripts
│   └── public/          # Static assets
├── pyproject.toml       # Python package config
├── ruff.toml            # Python linting configuration
└── dev.sh               # Start web dashboard
```

## Getting Started

### Option 1: Development Container (Recommended)

1. Install [VS Code](https://code.visualstudio.com/) and [Docker](https://www.docker.com/)
2. Clone the repo and open it in VS Code
3. When prompted, click "Reopen in Container" (or `Ctrl+Shift+P` → "Dev Containers: Reopen in Container")
4. The container will install all dependencies and run verification tests automatically

See [`.devcontainer/README.md`](.devcontainer/README.md) for details.

**Verify setup:**
```bash
.devcontainer/verify.sh
python -m tracekit --help
```

### Option 2: Local Installation

```bash
git clone https://github.com/ckdake/tracekit.git
cd tracekit
pip install -e .[dev]
pre-commit install
```

## Development Tools

**Python:**
- **Ruff** – Fast linting, formatting, and import sorting (replaces Black, Flake8, isort, Pylint)
- **MyPy** – Static type checking
- **Pytest** – Test runner with coverage
- **Pre-commit** – Git hooks for automated code quality

**Web:**
- **Node.js 18** – Runtime environment
- **Vite** – Build system and dev server
- **ESLint** – JavaScript linting
- **Stylelint** – CSS linting
- **Prettier** – Code formatting

## Development Commands

**Python:**
```bash
# Run tests
python -m pytest -v
python -m pytest --cov=tracekit --cov-report=term-missing -v

# Lint and format
ruff check tracekit/ tests/           # Check for issues
ruff check --fix tracekit/ tests/     # Auto-fix issues
ruff format tracekit/ tests/          # Format code

# Type checking
mypy tracekit/

# Run CLI
python -m tracekit --help
```

**Website:**
```bash
cd site/
npm install
npm run dev       # Development server (localhost:3000)
npm run build     # Build for production
npm run lint
npm run format
```

**Quality Assurance:**
```bash
pre-commit run --all-files
.devcontainer/verify.sh
```

## Web Dashboard

tracekit includes a local Flask web dashboard for inspecting configuration and database status:

```bash
./scripts/run-dev.sh
```

Visit http://localhost:5000 to see:
- Configuration status from `tracekit_config.json`
- Provider settings (enabled/disabled, priorities)
- Database information (size, tables, row counts)
- API endpoints for programmatic access

## Running via Docker

A pre-built image is available at `ghcr.io/ckdake/tracekit:latest`.

```bash
# Pull the latest published image
docker pull ghcr.io/ckdake/tracekit:latest

# Run with your local config mounted
docker run --rm -p 5000:5000 \
  -v $(pwd)/tracekit_config.json:/app/tracekit_config.json \
  ghcr.io/ckdake/tracekit:latest

# Verify health
curl http://localhost:5000/health
```

## Packaging & Release

1. Update the version in `pyproject.toml`
2. Build the package:
    ```bash
    python -m build
    ```
3. Upload to PyPI:
    ```bash
    twine upload dist/*
    ```

The GitHub Actions workflow handles automated CI checks on every pull request. The site is automatically deployed on merge to `main`.

## VS Code Integration

The development container automatically configures VS Code with:
- Format on save for Python, JavaScript, and CSS
- Automatic import organization
- Error highlighting across all languages
- Integrated terminal with the correct environment
- All required extensions pre-installed

**Available VS Code Tasks** (`Ctrl+Shift+P` → "Tasks: Run Task"):
- **Python: Run Tests** – Run all Python tests
- **Python: Lint All** – Run Python linting
- **Python: Format Code** – Auto-format Python code
- **Web App: Run Tests** – Run web dashboard tests
- **Site: Build** – Build the static website
- **Site: Dev Server** – Start the website dev server
- **DevContainer: Verify Setup** – Verify environment health
- **Full: Lint and Test** – Run all lint and test checks
