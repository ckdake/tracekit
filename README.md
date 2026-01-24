# tracekit

tracekit is a Python toolkit for aggregating, syncing, and analyzing your fitness activity data from multiple sources (Strava, RideWithGPS, spreadsheets, and local files). It is designed to be self-contained, non-destructive, and extensible.

🌐 **Website**: [tracekit.app](https://tracekit.app)
📦 **PyPI**: [pypi.org/project/tracekit](https://pypi.org/project/tracekit/)
📚 **Source**: [github.com/ckdake/tracekit](https://github.com/ckdake/tracekit)[CAUTION: This is under active development. Do not use it without reading every line of code!]

[![ruff](https://github.com/ckdake/tracekit/actions/workflows/ruff.yml/badge.svg)](https://github.com/ckdake/tracekit/actions/workflows/ruff.yml)
[![pytest](https://github.com/ckdake/tracekit/actions/workflows/pytest.yml/badge.svg)](https://github.com/ckdake/tracekit/actions/workflows/pytest.yml)
[![mypy](https://github.com/ckdake/tracekit/actions/workflows/mypy.yml/badge.svg)](https://github.com/ckdake/tracekit/actions/workflows/mypy.yml)
[![deploy-site](https://github.com/ckdake/tracekit/actions/workflows/deploy-site.yml/badge.svg)](https://github.com/ckdake/tracekit/actions/workflows/deploy-site.yml)

---

## Features

- Parse and import activity files (`.fit`, `.tcx`, `.gpx`, and compressed variants)
- Integrate with Strava and RideWithGPS APIs
- Store and manage activity metadata in a local SQLite database
- Command-line interface for authentication and data management
- **Web dashboard** for viewing configuration and database status (`./dev.sh`)
- Modular provider and file format architecture for easy extension
- Static website with documentation at [tracekit.app](https://tracekit.app)

---

## Quick Start

### Option 1: Development Container (Recommended)

The easiest way to get started is using the provided development container:

1. **Prerequisites**: Install [VS Code](https://code.visualstudio.com/) and [Docker](https://www.docker.com/)
2. **Open Repository**: Clone and open in VS Code
3. **Reopen in Container**: When prompted, click "Reopen in Container" or use `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"
4. **Wait for Setup**: The container will automatically install all dependencies and run verification tests
5. **Start Developing**: Everything is ready to go!

📋 See [`.devcontainer/README.md`](.devcontainer/README.md) for detailed container documentation.

**Verify Setup:**
```bash
.devcontainer/verify.sh  # Quick environment check
python -m tracekit --help  # Test CLI access
```

### Option 2: Local Installation

1. **Clone the repository:**
    ```sh
    git clone https://github.com/ckdake/tracekit.git
    cd tracekit
    ```

2. **Install dependencies:**
    ```sh
    pip install -e .[dev]  # Development installation
    # OR
    pip install .          # Regular installation
    ```

3. **Set up development tools:**
    ```sh
    pre-commit install     # Install git hooks
    ```

4. **Set up environment variables:**
   Create a `.env` file in the project root with the following variables:
   ```sh
   # Strava API credentials (required for Strava integration, generate with the auth-strava command)
   STRAVA_CLIENT_ID=your_client_id
   STRAVA_CLIENT_SECRET=your_client_secret
   STRAVA_ACCESS_TOKEN=your_access_token
   STRAVA_REFRESH_TOKEN=your_refresh_token
   STRAVA_TOKEN_EXPIRES=token_expiration_timestamp

   # RideWithGPS credentials (required for RWGPS integration)
   RIDEWITHGPS_EMAIL=your_email
   RIDEWITHGPS_PASSWORD=your_password
   RIDEWITHGPS_KEY=your_api_key

   # Garmin Connect credentials (required for Garmin integration)
   GARMIN_EMAIL=your_email
   GARMINTOKENS=~/.garminconnect
   ```
   Note: You can get Strava API credentials by creating an application at https://www.strava.com/settings/api,
   RideWithGPS credentials at https://ridewithgps.com/api, and Garmin Connect credentials by using your
   existing Garmin Connect account.

5. **Prepare your data:**
    - Place your exported Strava activity files in a folder such as `export_12345/` in the repo root.
    - If you're not using Strava export, place your files in `export_12345/activities/` in the repo root.
    - (Optional) Place your exercise spreadsheet at `~/Documents/exerciselog.xlsx`.

---

## Authenticating with Strava

To use Strava API features, you need to authenticate and get an access token.

1. **Set your Strava API credentials as environment variables:**
    ```sh
    export STRAVA_CLIENT_ID=your_client_id
    export STRAVA_CLIENT_SECRET=your_client_secret
    ```

2. **Run the Strava authentication command:**
    ```sh
    python -m tracekit auth-strava
    ```

    This will guide you through the OAuth process and print an access token.
    Set it in your environment:
    ```sh
    export STRAVA_ACCESS_TOKEN=your_access_token
    ```

---

## Authenticating with Garmin Connect

To use Garmin Connect API features, you need to authenticate and store OAuth tokens.

1. **Set your Garmin Connect credentials as environment variables (optional):**
    ```sh
    export GARMIN_EMAIL=your_email
    export GARMINTOKENS=~/.garminconnect
    ```

2. **Run the Garmin authentication command:**
    ```sh
    python -m tracekit auth-garmin
    ```

    This will prompt for your email and password, handle any required MFA, and automatically
    generate and store OAuth tokens that are valid for about a year. The tokens will be reused
    automatically for future API calls.

---

## Running tracekit

You can use the CLI for various commands:

```sh
python -m tracekit --help
python -m tracekit configure
python -m tracekit auth-strava
python -m tracekit auth-garmin
python -m tracekit pull --date 2025-08
python -m tracekit sync-month 2025-08
python -m tracekit reset --date 2025-08
```

- `configure` – Set up paths and API credentials.
- `auth-strava` – Authenticate with Strava and get an access token.
- `sync` – Sync and match activities from all sources.
- `help` – Show usage and documentation.

You can also use the Python API in your own scripts to process files, sync with providers, or analyze your data.

---

## Running Tests

tracekit uses [pytest](https://pytest.org/) for testing. To run all tests:

```sh
python -m pytest --cov=tracekit --cov-report=term-missing -v
```

Test files are in the `tests/` directory and mirror the package structure.

---

## Packaging & Publishing to PyPI

To prepare and publish the package:

1. **Update version and metadata in `setup.py` and `setup.cfg`.**
2. **Build the package:**
    ```sh
    python -m build
    ```
3. **Upload to PyPI (requires `twine`):**
    ```sh
    twine upload dist/*
    ```

---

## Contributing

PRs and issues are welcome! See the TODO section in this README for ideas and next steps.

---

## Development

This is a monorepo containing both the Python package and the static website.

### Repository Structure
```
tracekit/
├── .devcontainer/       # Development container configuration
├── .github/workflows/   # CI/CD pipelines
├── app/                 # Web dashboard (Flask)
├── tracekit/              # Python package source
├── tests/               # Python tests
├── site/                # Static website source
│   ├── src/             # Website source files
│   ├── scripts/         # Build scripts
│   └── dist/            # Built website (generated)
├── pyproject.toml       # Python package config
├── ruff.toml           # Python linting configuration
├── dev.sh              # Start web dashboard
└── README.md           # This file (also used for website)
```

### Web Dashboard

For local development, tracekit includes a simple web dashboard to view configuration and database status:

```bash
# Start the web dashboard
./dev.sh
```

Visit http://localhost:5000 to see:
- 📊 **Configuration status** from `tracekit_config.json`
- 🔌 **Provider settings** (enabled/disabled, priorities)
- 💾 **Database information** (size, tables, row counts)
- 🔗 **API endpoints** for programmatic access

The dashboard provides a quick way to verify your tracekit setup without running CLI commands.

### Development Tools

**Python Development:**
- **Ruff**: Fast linting, formatting, and import sorting (replaces Black, Flake8, isort, Pylint)
- **MyPy**: Static type checking
- **Pytest**: Test runner with coverage
- **Pre-commit**: Git hooks for automated code quality

**Web Development:**
- **Node.js 18**: Runtime environment
- **Vite**: Build system and dev server
- **ESLint**: JavaScript linting
- **Stylelint**: CSS linting
- **Prettier**: Code formatting

### Development Commands

**Python:**
```bash
# Run tests
python -m pytest -v

# Lint and format code
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

# Install dependencies
npm install

# Development server (localhost:3000)
npm run dev

# Build for production
npm run build

# Lint and format
npm run lint
npm run format
```

**Quality Assurance:**
```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Verify development environment
.devcontainer/verify.sh
```

### VS Code Integration

The development container automatically configures VS Code with:
- Format on save for all file types
- Automatic import organization
- Error highlighting for Python, JavaScript, CSS
- Integrated terminal with proper environment
- All necessary extensions pre-installed

**Available VS Code Tasks** (`Ctrl+Shift+P` → "Tasks: Run Task"):
- **Python: Run Tests** - Run all Python tests
- **Python: Lint All** - Run Python linting
- **DevContainer: Verify Setup** - Verify environment health

### Website Development

The website at [tracekit.app](https://tracekit.app) automatically includes content from this README.md file:

1. Start development server: `cd site && npm run dev`
2. Edit files in `site/src/` or update README.md
3. Site rebuilds automatically with changes
4. Build for production: `npm run build`

The website is automatically deployed when changes are pushed to the main branch.

---

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0). See the LICENSE file for details.

---

## Getting things back out into spreadsheet

    sqlite3 metadata.sqlite3
    .headers on
    .mode csv
    .output metadata.csv
    SELECT date,activity_type,location_name,city,state,temperature,equipment,duration_hms,max_speed,avg_heart_rate,max_heart_rate,calories,max_elevation,total_elevation_gain,with_names,avg_cadence,strava_id,garmin_id,ridewithgps_id,notes from ActivityMetadata where source="Main";
    .quit

## TODO

    * Next month to fix:  `python -m tracekit sync-month 2024-03`
    * File provider manually fixed, go through other providers and manually fix them to work the ~same way. make sure we're not making API calls if the month is synced.
    * Fix strava gear matching to work for running shoes.
    * Fix "create" in providers to create_from_activity, and get all that out of sync_month
    * Write some tests...
    * Get everything out of gpx files: https://pypi.org/project/gpxpy/  (basics are in, need to fill out metadata, add more fields to db!)
    * Get everything out of tcx files: https://pypi.org/project/python-tcxparser/ (basics are in, need to fill out metadata, add more fields to db!)
    * Get everything out of fit files: https://github.com/dtcooper/python-fitparse/ (basics are in, need to fill out metadata, add more fields to db!)
    * Get everything out of KML files: https://pypi.org/project/pykml/
    * Get everything out of a spreadsheet with headers: https://pypi.org/project/openpyxl/ (basics are in, work better with headers)

    * Output as all fit (lib already included)
    * Output as all tcx (lib already included)
    * Output as all gpx (lib already included)
    * Output as all kml (lib already included)
    * Output as all geojson: https://pypi.org/project/geojson/

    * Load files from S3 bucket or somewhere else instead of local: https://pypi.org/project/boto3/

    * What is in TrainingPeaks?
    * What is in Wandrer.earth?
    * What about the weather?
    * What about choochoo?
    * What else?

    * switch to fitdecode
