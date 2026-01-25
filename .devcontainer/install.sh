#!/bin/bash
set -e

echo "🚀 Setting up tracekit development environment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 1. Update system packages
if [ "${CI:-false}" = "true" ]; then
    print_status "Running in CI environment - skipping system package updates"
else
    print_status "Updating system packages..."
    # Ensure Yarn's GPG key is present so `apt-get update` won't fail with EXPKEYSIG
    print_status "Adding Yarn GPG key to apt keyring (if needed)..."
    if command -v gpg >/dev/null 2>&1; then
        curl -fsSL https://dl.yarnpkg.com/debian/pubkey.gpg \
            | gpg --dearmor \
            | sudo tee /usr/share/keyrings/yarn-archive-keyring.gpg >/dev/null || true
        echo "deb [signed-by=/usr/share/keyrings/yarn-archive-keyring.gpg] https://dl.yarnpkg.com/debian/ stable main" \
            | sudo tee /etc/apt/sources.list.d/yarn.list >/dev/null || true
    else
        curl -fsSL https://dl.yarnpkg.com/debian/pubkey.gpg | sudo apt-key add - || true
    fi

    print_status "Updating packages"
    sudo apt-get update
    sudo apt-get install -y \
        curl \
        wget \
        git \
        build-essential \
        sqlite3 \
        tree \
        jq
fi

# 2. Install Python development dependencies
print_status "Installing Python package in development mode..."
if pip3 install --user -e .[dev]; then
    print_success "Python package installed successfully"
else
    print_error "Failed to install Python package"
    exit 1
fi

# 3. Install additional Python tools for development
print_status "Installing additional Python development tools..."
pip3 install --user \
    pre-commit \
    types-pytz \
    types-python-dateutil \
    types-dateparser \
    types-tabulate

# 4. Set up Node.js environment for static site
print_status "Setting up Node.js environment..."
cd site

if [ -f "package.json" ]; then
    if npm install; then
        print_success "Node.js dependencies installed"
    else
        print_error "Failed to install Node.js dependencies"
        exit 1
    fi
else
    print_warning "No package.json found in site directory"
fi

cd ..

# 5. Install and configure pre-commit hooks
print_status "Setting up pre-commit hooks..."
if pre-commit install; then
    print_success "Pre-commit hooks installed"
else
    print_error "Failed to install pre-commit hooks"
    exit 1
fi

# 6. Configure git (if not already configured)
print_status "Checking git configuration..."
if ! git config --global user.name >/dev/null 2>&1; then
    print_warning "Git user.name not configured"
    echo "You may want to run: git config --global user.name 'Your Name'"
fi

if ! git config --global user.email >/dev/null 2>&1; then
    print_warning "Git user.email not configured"
    echo "You may want to run: git config --global user.email 'your.email@example.com'"
fi

# 7. Verify installations
print_status "Verifying installations..."

# Check Python tools
if python3 -c "import tracekit" 2>/dev/null; then
    print_success "tracekit package importable"
else
    print_error "tracekit package not importable"
fi

if command -v ruff >/dev/null 2>&1; then
    print_success "Ruff available ($(ruff --version))"
else
    print_error "Ruff not available"
fi

if command -v pre-commit >/dev/null 2>&1; then
    print_success "Pre-commit available ($(pre-commit --version))"
else
    print_error "Pre-commit not available"
fi

# Check Node.js tools
if command -v node >/dev/null 2>&1; then
    print_success "Node.js available ($(node --version))"
else
    print_error "Node.js not available"
fi

if command -v npm >/dev/null 2>&1; then
    print_success "npm available ($(npm --version))"
else
    print_error "npm not available"
fi

# 8. Run tests to ensure everything works
print_status "Running test suite to verify setup..."
if python3 -m pytest --tb=short -q; then
    print_success "All tests passed!"
else
    print_warning "Some tests failed - check output above"
fi

# 9. Run linting to verify code quality tools
print_status "Running linting checks..."
if ruff check tracekit/ tests/; then
    print_success "Ruff linting passed"
else
    print_warning "Ruff found some issues (see output above)"
fi

# 10. Check pre-commit hooks
print_status "Testing pre-commit hooks..."
if pre-commit run --all-files >/dev/null 2>&1; then
    print_success "Pre-commit hooks working"
else
    print_warning "Pre-commit hooks found issues to fix"
fi

echo ""
print_success "🎉 Development environment setup complete!"
echo ""
echo "Available commands:"
echo "  python -m tracekit --help              # Main CLI"
echo "  python -m pytest                     # Run tests"
echo "  ruff check tracekit/ tests/            # Lint code"
echo "  ruff format tracekit/ tests/           # Format code"
echo "  pre-commit run --all-files           # Run all pre-commit hooks"
echo "  cd site && npm run dev               # Start development server"
echo "  cd site && npm run build             # Build static site"
echo ""
print_status "Happy coding! 🐍✨"
