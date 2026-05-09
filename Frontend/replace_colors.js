const fs = require('fs');
const path = require('path');

const files = [
  'src/styles/components.css',
  'src/styles/landing.css',
  'src/styles/animation.css'
];

const replacements = [
  { regex: /rgba\s*\(\s*76\s*,\s*175\s*,\s*80\s*,([^)]+)\)/g, replacement: 'rgba(var(--primary-rgb),$1)' },
  { regex: /rgba\s*\(\s*129\s*,\s*199\s*,\s*132\s*,([^)]+)\)/g, replacement: 'rgba(var(--primary-rgb),$1)' },
  { regex: /rgba\s*\(\s*18\s*,\s*24\s*,\s*22\s*,([^)]+)\)/g, replacement: 'rgba(var(--bg-card-rgb),$1)' },
  { regex: /rgba\s*\(\s*11\s*,\s*15\s*,\s*12\s*,([^)]+)\)/g, replacement: 'rgba(var(--bg-primary-rgb),$1)' },
  { regex: /rgba\s*\(\s*22\s*,\s*29\s*,\s*25\s*,([^)]+)\)/g, replacement: 'rgba(var(--bg-surface-rgb),$1)' },
  { regex: /rgba\s*\(\s*22\s*,\s*32\s*,\s*26\s*,([^)]+)\)/g, replacement: 'rgba(var(--bg-surface-rgb),$1)' },
  { regex: /rgba\s*\(\s*26\s*,\s*38\s*,\s*30\s*,([^)]+)\)/g, replacement: 'rgba(var(--bg-surface-rgb),$1)' },
  { regex: /rgba\s*\(\s*13\s*,\s*18\s*,\s*15\s*,([^)]+)\)/g, replacement: 'rgba(var(--bg-secondary-rgb),$1)' }
];

files.forEach(file => {
  const filePath = path.join(__dirname, file);
  if (fs.existsSync(filePath)) {
    let content = fs.readFileSync(filePath, 'utf8');
    let original = content;
    replacements.forEach(({ regex, replacement }) => {
      content = content.replace(regex, replacement);
    });
    if (content !== original) {
      fs.writeFileSync(filePath, content);
      console.log(`Updated ${file}`);
    }
  } else {
    console.log(`File not found: ${file}`);
  }
});
