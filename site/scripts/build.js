import fs from 'fs';
import { marked } from 'marked';
import path from 'path';

// Read the main README.md
const readmePath = path.join(process.cwd(), '..', 'README.md');
const readmeContent = fs.readFileSync(readmePath, 'utf-8');

// Convert markdown to HTML
const readmeHtml = marked(readmeContent);

// Generate marketing homepage from index.template.html (no README content)
const indexTemplatePath = path.join(
    process.cwd(),
    'src',
    'index.template.html'
);
const indexTemplate = fs.readFileSync(indexTemplatePath, 'utf-8');
const indexOutputPath = path.join(process.cwd(), 'src', 'index.html');
fs.writeFileSync(indexOutputPath, indexTemplate);
console.log('✅ Generated index.html (marketing)');

// Generate developer page by injecting README into developer.template.html
const devTemplatePath = path.join(
    process.cwd(),
    'src',
    'developer.template.html'
);
if (fs.existsSync(devTemplatePath)) {
    const devTemplate = fs.readFileSync(devTemplatePath, 'utf-8');
    const devHtml = devTemplate.replace('{{README_CONTENT}}', readmeHtml);
    const devOutputPath = path.join(process.cwd(), 'src', 'developer.html');
    fs.writeFileSync(devOutputPath, devHtml);
    console.log('✅ Generated developer.html from README.md');
} else {
    console.log(
        'ℹ️ developer.template.html not found — skipping developer page generation'
    );
}
