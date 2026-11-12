// Copies KaTeX (maths rendering) into ../static/vendor/katex so it is served locally.
import { cpSync, mkdirSync } from 'node:fs';
const src = 'node_modules/katex/dist';
const out = '../static/vendor/katex';
mkdirSync(`${out}/contrib`, { recursive: true });
for (const f of ['katex.min.css', 'katex.min.js']) cpSync(`${src}/${f}`, `${out}/${f}`);
cpSync(`${src}/contrib/auto-render.min.js`, `${out}/contrib/auto-render.min.js`);
cpSync(`${src}/fonts`, `${out}/fonts`, { recursive: true });
console.log('KaTeX copied to', out);
