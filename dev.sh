#!/bin/bash

# tracekit Web App Development Server
# Runs the Flask development server for local testing

set -e

echo "🚀 Starting tracekit Web App Development Server..."
echo ""

# Check if we're in the right directory
if [ ! -f "tracekit_config.json" ]; then
    echo "❌ Error: tracekit_config.json not found in current directory"
    echo "   Please run this script from the tracekit project root directory"
    exit 1
fi

# Check if Flask is installed
if ! python -c "import flask" 2>/dev/null; then
    echo "📦 Installing Flask..."
    pip install flask
    echo ""
fi

echo "📍 Starting server at: http://localhost:5000"
echo "🔧 Dashboard: http://localhost:5000"
echo "⚙️  Config API: http://localhost:5000/api/config"
echo "💾 Database API: http://localhost:5000/api/database"
echo "❤️  Health Check: http://localhost:5000/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run the Flask app
export FLASK_ENV=development
export FLASK_DEBUG=1
python app/main.py
