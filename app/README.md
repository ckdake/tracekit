# tracekit Web Dashboard

A Flask-based web application providing a local development dashboard for tracekit configuration and database status.

## Features

- 📊 **Dashboard**: Overview of tracekit configuration and database status
- � **Sync Calendar**: Visual calendar showing provider sync status by month
- �🔌 **Provider Management**: View and understand provider priority and status
- 💾 **Database Info**: Table counts and database statistics
- 🔗 **API Endpoints**: JSON APIs for configuration and database data

## Quick Start

```bash
# Install dependencies
pip install flask

# Start the development server
python main.py
```

Visit http://localhost:5000 to access the dashboard.

## Testing

The web application has comprehensive test coverage in the `tests/` directory.

### Running Tests

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
python -m pytest tests/ -v

# Run tests with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing -v
```

### Test Structure

- **TestConfigLoading**: Configuration file parsing and error handling
- **TestDatabaseInfo**: Database connection and information extraction
- **TestSyncCalendar**: Provider sync calendar data processing
- **TestProviderSorting**: Provider priority sorting logic
- **TestWebRoutes**: Flask route responses and error handling
- **TestIntegration**: End-to-end application flow testing

### VS Code Tasks

The following VS Code tasks are available:

- `Web App: Run Tests` - Run the test suite
- `Web App: Run Tests with Coverage` - Run tests with coverage report
- `Web App: Start Server` - Start the development server

### CI/CD

Web app tests run independently from the main Python package tests in the `test-web-app` GitHub workflow. This ensures:

- ✅ Fast, focused testing for web application features
- ✅ Independent deployment and testing of web vs core functionality
- ✅ Clear separation of concerns between package and web app

## API Endpoints

- `GET /` - Main dashboard
- `GET /calendar` - Sync calendar view
- `GET /api/config` - Configuration JSON
- `GET /api/database` - Database information JSON
- `GET /health` - Health check endpoint

## Development

The web app automatically detects the tracekit configuration file (`tracekit_config.json`) in the current or parent directory and connects to the configured metadata database.

For development, the Flask app runs in debug mode with auto-reload enabled.

## Quick Start

From the project root directory:

```bash
# Run the development server
./dev.sh
```

The app will be available at: http://localhost:5000

## API Endpoints

- `GET /` - Main dashboard (HTML)
- `GET /api/config` - Configuration data (JSON)
- `GET /api/database` - Database information (JSON)
- `GET /health` - Health check (JSON)

## Development

The web app automatically:
- Reads `tracekit_config.json` from the parent directory
- Connects to the configured SQLite database
- Provides real-time status information

## Future Plans

This local development app will eventually be deployed to `app.tracekit.net` for remote access to tracekit status and management.

## Requirements

- Python 3.7+
- Flask 3.0+
- Access to `tracekit_config.json` and the configured SQLite database

## Structure

```
app/
├── main.py              # Flask application
├── templates/
│   └── index.html       # Dashboard template
└── README.md           # This file
```
