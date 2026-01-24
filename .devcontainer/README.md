# tracekit Development Container

This development container provides a complete, reproducible development environment for the tracekit project with all necessary tools and dependencies pre-installed.

## What's Included

### Core Development Environment
- **Python 3.13** with tracekit package installed in development mode
- **Node.js 18** for static site development
- **Git** with proper configuration

### Python Development Tools
- **Ruff** - Fast Python linter and formatter (replaces Black, Flake8, isort, Pylint)
- **MyPy** - Static type checker with type stubs
- **Pytest** - Testing framework with coverage support
- **Pre-commit** - Git hooks for automated code quality checks

### Web Development Tools
- **ESLint** - JavaScript linting
- **Prettier** - Code formatting for JS/CSS/HTML/JSON
- **Stylelint** - CSS linting
- **Vite** - Fast build tool for the static site

### VS Code Extensions
- Python support (Pylance, MyPy, Ruff)
- SQLite viewer for database inspection
- Tailwind CSS IntelliSense
- ESLint and Prettier integration
- Stylelint integration

## Quick Start

1. Open this repository in VS Code
2. When prompted, click "Reopen in Container"
3. Wait for the container to build and setup to complete
4. Start developing!

## Available Commands

### Python Development
```bash
# Run the main CLI
python -m tracekit --help

# Run tests
python -m pytest
python -m pytest -v                    # Verbose output
python -m pytest tests/specific_test.py # Run specific test

# Code quality
ruff check tracekit/ tests/               # Lint code
ruff format tracekit/ tests/              # Format code
ruff check --fix tracekit/ tests/         # Auto-fix issues

# Pre-commit hooks
pre-commit run --all-files              # Run all hooks
pre-commit run ruff                     # Run specific hook
```

### Web Development
```bash
# Navigate to site directory
cd site

# Install dependencies (done automatically)
npm install

# Development server
npm run dev

# Build for production
npm run build

# Lint and format
npm run lint
npm run format
```

### Database Management
```bash
# View the SQLite database using VS Code extension
# Or use command line:
sqlite3 metadata.sqlite3

# Reset database
python -m tracekit reset
```

## Directory Structure

```
/workspaces/tracekit/
├── .devcontainer/
│   ├── devcontainer.json          # Container configuration
│   ├── install.sh                 # Setup script
│   └── README.md                  # This file
├── tracekit/                        # Python package
├── tests/                         # Test suite
├── site/                          # Static website
├── .github/workflows/             # CI/CD pipelines
├── pyproject.toml                 # Python project config
├── ruff.toml                      # Ruff configuration
└── .pre-commit-config.yaml        # Pre-commit hooks
```

## Development Workflow

1. **Code**: Write code with automatic formatting and linting
2. **Test**: Run tests frequently (`python -m pytest`)
3. **Commit**: Pre-commit hooks automatically check code quality
4. **Push**: GitHub Actions run comprehensive checks

## Configuration Files

### Python (`ruff.toml`)
- Line length: 120 characters
- Target: Python 3.13
- Comprehensive rule set with sensible ignores
- Auto-fixing enabled

### JavaScript (`site/.eslintrc.json`)
- Standard configuration
- ES2022 features
- Browser environment

### Pre-commit (`.pre-commit-config.yaml`)
- Ruff for Python linting/formatting
- ESLint for JavaScript
- Prettier for general formatting
- Various utility hooks

## Troubleshooting

### Container Won't Start
- Ensure Docker is running
- Try rebuilding: `Ctrl+Shift+P` → "Dev Containers: Rebuild Container"

### Dependencies Missing
- Run the setup script manually: `.devcontainer/install.sh`
- Check the installation logs in the VS Code terminal

### Pre-commit Hooks Failing
- Run manually: `pre-commit run --all-files`
- Update hooks: `pre-commit autoupdate`

### Node Dependencies Issues
```bash
cd site
rm -rf node_modules package-lock.json
npm install
```

### Python Package Issues
```bash
pip install --user -e .[dev] --force-reinstall
```

## Environment Variables

The container sets up these environment variables:
- `PYTHONPATH`: Set to `/workspaces/tracekit`
- `tracekit_CONFIG_PATH`: Points to config file location

## VS Code Settings

The container configures VS Code with:
- Format on save enabled
- Automatic import organization
- Ruff as default Python formatter
- ESLint and Prettier integration
- Proper working directories for multi-project setup

## Port Forwarding

- Port 3000: Vite development server (automatically forwarded)

## File Watching

The container is configured to:
- Watch Python files for changes (auto-reload during development)
- Hot reload for the Vite development server
- Auto-run pre-commit hooks on git commits

## Performance Tips

- The container uses bind mounts for optimal file watching performance
- Node modules are installed inside the container for faster access
- Python packages are installed in user space to avoid permission issues

## Support

If you encounter issues with the development container:
1. Check this README for common solutions
2. Review the setup script output in VS Code terminal
3. Rebuild the container if needed
4. Check the main project documentation in `DEVELOPMENT.md`
