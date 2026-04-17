/**
 * Mermaid initialisation — bundled (no CDN).
 *
 * Problem: Starlight/Expressive Code renders ```mermaid blocks as:
 *   <pre data-language="mermaid"><code><div class="ec-line">…</div></code></pre>
 * Mermaid's engine only processes elements with class="mermaid" and never
 * sees the EC-wrapped nodes, so every diagram shows as code text.
 *
 * Fix: on each page load, find all EC mermaid blocks, extract their raw text
 * content (stripping EC spans), replace them with <div class="mermaid">, then
 * call mermaid.run() on those nodes.
 *
 * Also registers the ELK layout engine — all diagrams in docs/ use
 * `layout: elk` in their frontmatter; without this they silently fall back
 * to dagre which produces very different layouts.
 *
 * Runs on initial load (DOMContentLoaded / immediately if already ready) and
 * on `astro:page-load` if Starlight's client-side navigation (View
 * Transitions) is enabled. This site ships without View Transitions, so
 * listening only for `astro:page-load` would leave every diagram unrendered.
 */

import mermaid from 'mermaid';
import elkLayouts from '@mermaid-js/layout-elk';

let initialized = false;

function convertAndRender() {
  const ecBlocks = document.querySelectorAll<HTMLElement>('pre[data-language="mermaid"]');
  if (ecBlocks.length === 0) return;

  const converted: HTMLElement[] = [];
  ecBlocks.forEach(pre => {
    const div = document.createElement('div');
    div.className = 'mermaid';
    // Expressive Code wraps each source line in <div class="ec-line">. Using
    // .textContent concatenates all lines with no separator, producing a
    // single-line blob that Mermaid cannot parse. Reconstruct the source by
    // joining each line's text with '\n'.
    const lines = pre.querySelectorAll<HTMLElement>('.ec-line');
    const source = lines.length > 0
      ? [...lines].map(l => l.textContent ?? '').join('\n')
      : (pre.textContent ?? '');
    div.textContent = source;
    (pre.closest('figure') ?? pre).replaceWith(div);
    converted.push(div);
  });

  if (!initialized) {
    mermaid.registerLayoutLoaders(elkLayouts);
    mermaid.initialize({ startOnLoad: false, theme: 'default' });
    initialized = true;
  }

  mermaid.run({ nodes: converted });
}

document.addEventListener('astro:page-load', convertAndRender);

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', convertAndRender, { once: true });
} else {
  convertAndRender();
}
