#!/usr/bin/env node
/**
 * Convert Jupyter notebooks into Starlight markdown pages.
 *
 * Source roots → dest directories (under src/content/docs/notebooks/):
 *
 *   tests/e2e/notebooks/platform-tests/**.ipynb  → e2e/
 *   docs/notebooks/tutorials/**.ipynb            → tutorial/
 *   docs/notebooks/reference/**.ipynb            → reference/
 *   docs/notebooks/uat/**.ipynb                  → uat/
 *
 * The converter is pure Node.js — no Python, no nbconvert. It exploits the
 * fact that every .ipynb in this repo has been run through nbstripout, so
 * there are zero cell outputs to worry about. Markdown cells are written
 * verbatim; code cells become ```python fenced blocks. Titles are derived
 * from the first markdown cell (stripping the repo's `<div class="nb-header">
 * <h1 class="nb-header__title">...</h1>` wrapper if present), falling back
 * to the filename.
 *
 * Invoked automatically via the `prebuild` npm script so `npm run build`
 * always sees a fresh notebooks tree under src/content/docs/notebooks/.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const REPO_ROOT = path.resolve(PKG_ROOT, '..', '..');
const DEST_ROOT = path.join(PKG_ROOT, 'src', 'content', 'docs', 'notebooks');

const SOURCE_MAPPINGS = [
  { label: 'e2e', src: path.join(REPO_ROOT, 'tests', 'e2e', 'notebooks', 'platform-tests') },
  { label: 'tutorial', src: path.join(REPO_ROOT, 'docs', 'notebooks', 'tutorials') },
  { label: 'reference', src: path.join(REPO_ROOT, 'docs', 'notebooks', 'reference') },
  { label: 'uat', src: path.join(REPO_ROOT, 'docs', 'notebooks', 'uat') },
];

const EXCLUDED_DIRS = new Set(['__pycache__', '.ipynb_checkpoints', 'node_modules', '.git', 'lib']);

/** Walk a directory, yielding every .ipynb file (excluding EXCLUDED_DIRS). */
function* walkIpynb(dir) {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    if (EXCLUDED_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walkIpynb(full);
    } else if (entry.isFile() && entry.name.endsWith('.ipynb')) {
      yield full;
    }
  }
}

/** Join an .ipynb cell's `source` field (which may be a string or array of strings). */
function joinSource(source) {
  if (typeof source === 'string') return source;
  if (Array.isArray(source)) return source.join('');
  return '';
}

/**
 * Rewrite cross-notebook links from Jupyter/MkDocs convention to Starlight routes.
 *
 *   foo.ipynb          → foo/                (Starlight route = directory URL)
 *   foo.ipynb#section  → foo/#section        (preserve anchors)
 *   _index.ipynb       → ./                  (section landings become parent dir)
 *   ../bar/_index.ipynb → ../bar/            (cross-section landing link)
 *
 * Handles both markdown-style `[text](url)` and HTML-style `href="url"`/`href='url'`.
 * Leaves absolute URLs (http://, /, #frag-only) alone.
 */
function rewriteNotebookLinks(src) {
  // Pass 1: strip trailing _index.ipynb from the path component, leaving
  // the trailing "/" so links like ../bar/_index.ipynb become ../bar/
  src = src.replace(
    /(\[[^\]\n]*\]\()([^)\n]*?)_index\.ipynb(#[^)\n]*)?\)/g,
    (_m, prefix, path, frag = '') => `${prefix}${path}${frag})`,
  );
  src = src.replace(
    /(href\s*=\s*["'])([^"'\n]*?)_index\.ipynb(#[^"'\n]*)?(["'])/g,
    (_m, prefix, path, frag = '', quote) => `${prefix}${path}${frag}${quote}`,
  );

  // Pass 2: replace any remaining ".ipynb" with "/" — Starlight directory URL
  src = src.replace(
    /(\[[^\]\n]*\]\()([^)\n]*?)\.ipynb(#[^)\n]*)?\)/g,
    (_m, prefix, path, frag = '') => `${prefix}${path}/${frag})`,
  );
  src = src.replace(
    /(href\s*=\s*["'])([^"'\n]*?)\.ipynb(#[^"'\n]*)?(["'])/g,
    (_m, prefix, path, frag = '', quote) => `${prefix}${path}/${frag}${quote}`,
  );

  return src;
}

/**
 * Derive a human-readable page title from the notebook contents.
 * Priority:
 *   1. <h1 class="nb-header__title">...</h1> inside the first markdown cell
 *      (the repo's custom notebook header convention)
 *   2. First `# Heading` line from any markdown cell
 *   3. Filename humanized (snake/kebab → words, drop numeric prefix)
 */
function deriveTitle(cells, fallbackFile) {
  // 1. nb-header__title pattern
  for (const cell of cells) {
    if (cell.cell_type !== 'markdown') continue;
    const src = joinSource(cell.source);
    const hdr = src.match(/<h1[^>]*class="[^"]*nb-header__title[^"]*"[^>]*>([\s\S]*?)<\/h1>/i);
    if (hdr) return stripHtml(hdr[1]).trim();
  }
  // 2. First `# ...` markdown heading
  for (const cell of cells) {
    if (cell.cell_type !== 'markdown') continue;
    const src = joinSource(cell.source);
    const m = src.match(/^\s{0,3}#\s+(.+?)\s*$/m);
    if (m) return stripHtml(m[1]).trim();
  }
  // 3. Filename fallback
  const base = path.basename(fallbackFile, '.ipynb');
  return humanizeFilename(base);
}

function stripHtml(s) {
  return s.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');
}

function humanizeFilename(base) {
  // Drop leading "NN_" or "NN-" numeric prefix for display purposes
  const noPrefix = base.replace(/^\d+[_-]/, '');
  const words = noPrefix.replace(/[_-]+/g, ' ').trim();
  if (!words) return base;
  return words.replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Pick a fence length that the cell source cannot escape.
 * If the source contains "```" (e.g. markdown embedded in a raw cell), bump to
 * 4 or more backticks. Code cells in this repo are all Python and don't use
 * backticks, but be defensive.
 */
function chooseFence(src) {
  let n = 3;
  const re = /(`{3,})/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    if (m[1].length >= n) n = m[1].length + 1;
  }
  return '`'.repeat(n);
}

/** YAML-escape a title value for frontmatter. */
function yamlQuote(s) {
  // Use double quotes and escape embedded "
  return '"' + s.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
}

function convertNotebook(nbPath, destPath) {
  let nb;
  try {
    nb = JSON.parse(fs.readFileSync(nbPath, 'utf-8'));
  } catch (err) {
    console.warn(`  SKIP (invalid JSON): ${path.relative(REPO_ROOT, nbPath)} — ${err.message}`);
    return false;
  }
  const cells = Array.isArray(nb.cells) ? nb.cells : [];
  const title = deriveTitle(cells, nbPath);

  const out = [];
  out.push('---');
  out.push(`title: ${yamlQuote(title)}`);
  out.push('---');
  out.push('');

  for (const cell of cells) {
    const src = joinSource(cell.source).replace(/\s+$/g, '');
    if (!src) continue;

    if (cell.cell_type === 'markdown') {
      out.push(rewriteNotebookLinks(src));
      out.push('');
    } else if (cell.cell_type === 'code') {
      const fence = chooseFence(src);
      out.push(`${fence}python`);
      out.push(src);
      out.push(fence);
      out.push('');
    } else if (cell.cell_type === 'raw') {
      // Raw cells — emit as a plain HTML comment so nothing executes
      out.push('<!-- raw cell -->');
      out.push(rewriteNotebookLinks(src));
      out.push('<!-- /raw cell -->');
      out.push('');
    }
  }

  fs.mkdirSync(path.dirname(destPath), { recursive: true });
  fs.writeFileSync(destPath, out.join('\n'));
  return true;
}

/** Remove and recreate a directory. */
function resetDir(dir) {
  if (fs.existsSync(dir)) fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
}

function main() {
  const start = Date.now();

  // Top-level notebooks dir: clean and rebuild.
  resetDir(DEST_ROOT);

  // Landing page for the section — simple frontmatter page.
  fs.writeFileSync(
    path.join(DEST_ROOT, 'index.md'),
    [
      '---',
      'title: "Notebooks"',
      'description: "Jupyter notebooks rendered as static pages — tutorials, SDK reference, end-to-end tests, and UAT."',
      '---',
      '',
      'This section collects the platform\'s Jupyter notebooks, converted to static pages at build time.',
      'The notebooks remain the source of truth; this rendering is generated from the `.ipynb` files on every build.',
      '',
      '- **Tutorial** — hands-on walkthroughs for analysts (`docs/notebooks/tutorials/`)',
      '- **Reference** — API reference notebooks per SDK resource (`docs/notebooks/reference/`)',
      '- **E2E** — end-to-end platform test notebooks (`tests/e2e/notebooks/platform-tests/`)',
      '- **UAT** — user acceptance test notebooks (`docs/notebooks/uat/`)',
      '',
      'To run any of these notebooks interactively, open them in JupyterHub with a configured `GraphOLAPClient`.',
      '',
    ].join('\n'),
  );

  let totalConverted = 0;
  let totalSkipped = 0;

  for (const { label, src } of SOURCE_MAPPINGS) {
    const destSubdir = path.join(DEST_ROOT, label);
    fs.mkdirSync(destSubdir, { recursive: true });

    let converted = 0;
    let skipped = 0;
    for (const nbPath of walkIpynb(src)) {
      const rel = path.relative(src, nbPath);
      // Starlight ignores files with leading underscore (treats them as partials).
      // The source tree uses the Hugo convention _index.ipynb for section landings;
      // rename those to index.md (Starlight's section-landing convention).
      // For other leading-underscore files, strip the prefix so they render.
      const relMapped = rel.replace(/(^|\/)_index\.ipynb$/, '$1index.ipynb')
                           .replace(/(^|\/)_([^/]+)\.ipynb$/, '$1$2.ipynb');
      const destPath = path.join(destSubdir, relMapped).replace(/\.ipynb$/, '.md');
      const ok = convertNotebook(nbPath, destPath);
      if (ok) converted += 1;
      else skipped += 1;
    }
    totalConverted += converted;
    totalSkipped += skipped;
    console.log(`  ${label.padEnd(9)} ${String(converted).padStart(3)} notebooks → ${path.relative(PKG_ROOT, destSubdir)}`);
  }

  const elapsed = Date.now() - start;
  console.log(
    `build-notebooks: converted ${totalConverted} notebook${totalConverted === 1 ? '' : 's'}` +
      (totalSkipped ? `, skipped ${totalSkipped}` : '') +
      ` in ${elapsed}ms`,
  );
}

main();
