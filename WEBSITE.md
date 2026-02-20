# Website

The static website at [tracekit.app](https://tracekit.app) lives in the `site/` directory. It is built with Vite and automatically deployed to GitHub Pages on every push to `main`.

## Structure

```
site/
├── src/
│   ├── index.html              # Main page (generated from template)
│   ├── index.template.html     # Template for main page
│   ├── developer.html          # Developer page (generated)
│   ├── developer.template.html # Template for developer page
│   └── assets/
│       ├── css/
│       ├── js/
│       └── img/
├── scripts/
│   └── build.js                # Custom build script
├── public/
│   └── CNAME                   # Custom domain config
├── package.json
├── vite.config.js
└── COLORS.md                   # Color palette reference
```

## Local Development

```bash
cd site/
npm install
npm run dev     # Starts dev server at localhost:3000
```

The site rebuilds automatically when you change files in `site/src/`.

## Building for Production

```bash
cd site/
npm run build   # Output goes to site/dist/
```

## Linting & Formatting

```bash
cd site/
npm run lint    # ESLint + Stylelint
npm run format  # Prettier
```

## Content

The website content is authored directly in the template HTML files in `site/src/`. The build script (`scripts/build.js`) renders the templates into final HTML.

## Deployment

The site is automatically deployed via the `deploy-site` GitHub Actions workflow when changes are pushed to the `main` branch. The workflow:

1. Installs Node.js dependencies
2. Runs `npm run build`
3. Publishes `site/dist/` to GitHub Pages

The custom domain `tracekit.app` is configured via `site/public/CNAME`.

[![deploy-site](https://github.com/ckdake/tracekit/actions/workflows/deploy-site.yml/badge.svg)](https://github.com/ckdake/tracekit/actions/workflows/deploy-site.yml)
