#!/bin/bash
# Quick verification script for devcontainer functionality

set -e

if [ "${CI:-false}" = "true" ]; then
    echo "🧪 Running devcontainer verification tests (CI mode)..."
else
    echo "🧪 Running devcontainer verification tests..."
fi

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

success() {
    echo -e "${GREEN}✓${NC} $1"
}

failure() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Test Python environment
info "Testing Python environment..."
python3 -c "import tracekit; print(f'tracekit version: {tracekit.__version__}')" && success "tracekit package importable" || failure "tracekit package not importable"

# Test Ruff
info "Testing Ruff..."
ruff --version >/dev/null && success "Ruff available" || failure "Ruff not available"

# Test pre-commit
info "Testing pre-commit..."
pre-commit --version >/dev/null && success "Pre-commit available" || failure "Pre-commit not available"

# Test Node.js
info "Testing Node.js environment..."
node --version >/dev/null && success "Node.js available" || failure "Node.js not available"

# Test npm dependencies
info "Testing npm dependencies..."
cd site && npm list --silent >/dev/null 2>&1 && success "npm dependencies installed" || failure "npm dependencies missing"
cd ..

# Test code quality tools
info "Testing code quality..."
ruff check tracekit/ tests/ >/dev/null && success "Ruff linting passes" || failure "Ruff linting fails"

# Test basic functionality
info "Testing basic functionality..."
python3 -m tracekit --help >/dev/null && success "CLI accessible" || failure "CLI not accessible"

# Test pytest
info "Testing pytest..."
if [ "${CI:-false}" = "true" ]; then
    python3 -m pytest --co -q >/dev/null && success "Tests discoverable" || failure "Tests not discoverable"
else
    python3 -m pytest --co -q >/dev/null && success "Tests discoverable" || failure "Tests not discoverable"
fi

echo ""
success "🎉 All devcontainer verification tests passed!"
echo ""
echo "Your development environment is ready to use:"
echo "  • Python 3.13 with tracekit package"
echo "  • Ruff for fast linting and formatting"
echo "  • Pre-commit hooks configured"
echo "  • Node.js 18 with site dependencies"
echo "  • VS Code extensions ready"
echo ""
echo "Try running: python -m tracekit --help"
