#!/bin/bash
# tracekit Site Development Helper Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚴‍♂️ tracekit Site Development Helper${NC}"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo -e "${RED}❌ Error: This script must be run from the site/ directory${NC}"
    echo "Please run: cd site && ./dev.sh"
    exit 1
fi

# Show available commands
show_help() {
    echo -e "${YELLOW}Available commands:${NC}"
    echo "  build   - Build the site for production"
    echo "  dev     - Start development server"
    echo "  preview - Preview production build"
    echo "  lint    - Lint JavaScript and CSS"
    echo "  format  - Format code with Prettier"
    echo "  clean   - Clean build artifacts"
    echo "  help    - Show this help"
}

case "${1:-help}" in
    "build")
        echo -e "${GREEN}🔨 Building site...${NC}"
        npm run build
        echo -e "${GREEN}✅ Build complete! Files are in dist/${NC}"
        ;;
    "dev")
        echo -e "${GREEN}🚀 Starting development server...${NC}"
        echo -e "${YELLOW}💡 The site will be available at http://localhost:3000${NC}"
        npm run dev
        ;;
    "preview")
        echo -e "${GREEN}👀 Starting preview server...${NC}"
        npm run preview
        ;;
    "lint")
        echo -e "${GREEN}🔍 Linting code...${NC}"
        npm run lint
        ;;
    "format")
        echo -e "${GREEN}💅 Formatting code...${NC}"
        npm run format
        echo -e "${GREEN}✅ Formatting complete!${NC}"
        ;;
    "clean")
        echo -e "${YELLOW}🧹 Cleaning build artifacts...${NC}"
        rm -rf dist/ src/index.html node_modules/.vite
        echo -e "${GREEN}✅ Clean complete!${NC}"
        ;;
    "help"|*)
        show_help
        ;;
esac
