# tracekit Website

Static website for [tracekit.net](https://tracekit.net), automatically built from the main README.md.

## Development

The website development is now integrated into the main development workflow. See the main [README.md](../README.md) for comprehensive development instructions.

**Quick start:**

```bash
npm install      # Install dependencies
npm run dev      # Start dev server (localhost:3000)
npm run build    # Build for production
```

**Using devcontainer (recommended):**

1. Open repository in VS Code
2. Reopen in container when prompted
3. Navigate to `site/` directory
4. Run `npm run dev`

## How it works

1. `scripts/build.js` converts `../README.md` to HTML
2. Injects it into `src/index.template.html`
3. Vite builds the final static site
4. GitHub Actions deploys to Pages automatically

## Development Tools

The site uses the same development tools as the main project:

-   **ESLint** for JavaScript linting
-   **Stylelint** for CSS linting
-   **Prettier** for code formatting
-   **Pre-commit hooks** for automated quality checks

All tools are configured in the devcontainer and work seamlessly with VS Code.

-   Changes are pushed to the `site/` directory
-   Changes are made to the main `README.md` file

The deployment workflow is defined in `.github/workflows/deploy-site.yml`.

## Custom Domain

The site is served at `tracekit.net` via the `CNAME` file in `public/`.

## Files

-   `src/index.template.html` - HTML template with placeholder for README content
-   `src/assets/css/style.css` - Stylesheet for the site
-   `src/assets/js/main.js` - JavaScript functionality
-   `scripts/build.js` - Build script that processes README.md
-   `vite.config.js` - Vite configuration
-   `public/CNAME` - Custom domain configuration
