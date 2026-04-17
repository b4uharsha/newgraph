---
title: "Notebook Design System"
scope: hsbc
---

# Notebook Design System

## Overview

The Notebook Design System provides consistent, accessible styling for Jupyter notebooks in the Graph OLAP Platform. Based on [Airbnb's Design Language System (DLS)](https://karrisaarinen.com/dls/) principles, it delivers professional documentation that renders immediately without code execution.

## Prerequisites

Documents to read first:
- [`docs/document.structure.md`](--/document.structure.md) - Documentation standards
- [`docs/foundation/architectural.guardrails.md`](--/foundation/architectural.guardrails.md) - Platform constraints

## Constraints

### Hard Requirements

1. **No inline CSS** - All styling via global CSS loaded by JupyterHub
2. **No emoji icons** - Use Lucide icons via CSS mask technique
3. **WCAG AA compliance** - All color combinations must pass 4.5:1 contrast ratio
4. **BEM naming** - All CSS classes use `nb-block__element--modifier` pattern
5. **Token-first** - No hardcoded colors, sizes, or spacing values

### Design Principles (Airbnb DLS)

**Reference:** ADR-062: Airbnb DLS Notebook Design System

| Principle | Description | Implementation |
|-----------|-------------|----------------|
| **Unified** | Each piece is part of a greater whole | Single CSS file, shared tokens |
| **Universal** | Welcoming and accessible | WCAG AA, screen reader support |
| **Iconic** | Focused and bold communication | Type badges, numbered sections |
| **Conversational** | Motion brings life | Hover effects, transitions |

### Pure Markdown Rendering

**Reference:** ADR-087: Pure Markdown over Python HTML Rendering

All styled content uses **pure Markdown cells** with HTML, not Python code:

```markdown
<!-- ✅ Correct: Markdown cell with HTML -->
<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Note</div>
    <div class="nb-callout__body">Important information here.</div>
  </div>
</div>
```

```python
# ❌ Incorrect: Python code rendering HTML
from IPython.display import display, HTML
display(HTML('<div class="nb-callout">...</div>'))
```

**Benefits of pure Markdown:**
- Instant rendering - Content visible on notebook open
- No kernel needed - Works without Python execution
- GitHub preview - HTML renders in notebook viewer
- Accessible - Content available to screen readers immediately

### CSS Distribution

**Reference:** ADR-091: SDK Embedded CSS Distribution

CSS is embedded in the **SDK package** at `graph_olap/styles/notebook.css` and deployed via init container:

```
SDK Package                    JupyterHub Pod
┌─────────────┐               ┌─────────────────┐
│ graph_olap/ │   pip install │ Init Container  │
│ styles/     │──────────────►│ cp CSS to       │
│ notebook.css│               │ ~/.jupyter/     │
└─────────────┘               │ custom/         │
                              └─────────────────┘
```

**Access from Python:**

```python
from graph_olap.notebook import get_css_path, get_css_content

# Get path to embedded CSS
css_path = get_css_path()

# Get CSS content as string
css_content = get_css_content()
```

### Three-Tier Notebook Organization

**Reference:** ADR-092: Three-Tier Notebook Documentation Hierarchy

Notebooks are organized following Google Developer Documentation guidelines:

```
docs/notebooks/
├── tutorials/           # Learning-focused, step-by-step
│   ├── getting-started/
│   ├── sdk-basics/
│   └── graph-algorithms/
│
├── reference/           # Task-focused, API documentation
│   ├── sdk/
│   └── algorithms/
│
└── examples/            # Real-world use cases (planned)

tests/e2e/notebooks/
└── platform-tests/      # Pure E2E tests (19 notebooks)
```

**Tier Definitions:**

| Tier | Purpose | Style | Length |
|------|---------|-------|--------|
| **Tutorials** | Teach concepts | Narrative, step-by-step | 15-30 min |
| **Reference** | Document APIs | Structured, comprehensive | Variable |
| **Examples** | Show applications | Real-world, complete | 20-45 min |

**Navigation:** Each folder contains `_index.ipynb` providing entry points.

---

## Design

### Architecture

```
JupyterHub                     Notebooks
    |                              |
    v                              v
custom.js -----> injects -----> notebook.css
                                   |
                                   v
                           All nb-* classes
                           available globally
```

**CSS Source:** `docs/notebooks/assets/styles/notebook.css`

**CSS Injection:** `tools/jupyterhub/custom.js`

### Design Tokens

Design tokens provide the foundation for visual consistency:

#### Typography

| Token | Value | Usage |
|-------|-------|-------|
| `--nb-font-sans` | System font stack | Body text |
| `--nb-font-mono` | Monospace stack | Code |
| `--nb-text-xs` to `--nb-text-3xl` | 1.25 modular scale | Font sizes |

#### Colors

| Category | Surface | Text | Border |
|----------|---------|------|--------|
| **Primary** | `#ffffff` | `#1e293b` | `#e2e8f0` |
| **Muted** | `#f8fafc` | `#64748b` | - |
| **Info** | `#eff6ff` | `#1e40af` | `#bfdbfe` |
| **Success** | `#f0fdf4` | `#166534` | `#bbf7d0` |
| **Warning** | `#fffbeb` | `#92400e` | `#fde68a` |
| **Tip** | `#f0fdfa` | `#115e59` | `#99f6e4` |

#### Spacing

4px base unit with consistent scale:

| Token | Value | Pixels |
|-------|-------|--------|
| `--nb-space-1` | 0.25rem | 4px |
| `--nb-space-2` | 0.5rem | 8px |
| `--nb-space-3` | 0.75rem | 12px |
| `--nb-space-4` | 1rem | 16px |
| `--nb-space-6` | 1.5rem | 24px |
| `--nb-space-8` | 2rem | 32px |

#### Motion

| Token | Value | Usage |
|-------|-------|-------|
| `--nb-duration-fast` | 150ms | Hover states |
| `--nb-duration-normal` | 250ms | Transitions |
| `--nb-easing-default` | cubic-bezier(0.4, 0, 0.2, 1) | Smooth easing |

### Component Library

#### Core Components

| Component | Class | Purpose |
|-----------|-------|---------|
| Header | `nb-header` | Notebook title, metadata, tags |
| Section | `nb-section` | Numbered section headers |
| Callout | `nb-callout` | Info/success/warning/tip boxes |
| Objectives | `nb-objectives` | Learning goals list |
| Takeaways | `nb-takeaways` | Summary checklist |
| Figure | `nb-figure` | Image with caption |
| Details | `nb-details` | Collapsible content |
| API Ref | `nb-api-ref` | Function signature cards |

#### New Components (Airbnb Review)

| Component | Class | Purpose |
|-----------|-------|---------|
| Type Badge | `nb-header__type` | Notebook category indicator |
| Difficulty | `nb-difficulty` | Visual difficulty indicator (3 dots) |
| Progress | `nb-progress` | Tutorial progress bar |
| Card | `nb-card` | Linked notebook cards |
| Card Grid | `nb-card-grid` | Responsive card layout |
| Link List | `nb-link-list` | Navigation links |

### Icon System

Icons use Lucide SVGs embedded as data URIs with CSS `mask-image`:

```css
.nb-callout__icon {
  width: 20px;
  height: 20px;
  background-color: currentColor;  /* Inherits text color */
  mask-image: var(--icon-info);
  mask-size: contain;
}
```

**Benefits:**
- Icons colored by `currentColor` (semantic)
- No external dependencies
- Consistent cross-platform rendering (unlike emoji)
- Works with all callout variants automatically

**Available Icons:**
- `--icon-info` - Circle with "i"
- `--icon-check-circle` - Checkmark in circle
- `--icon-alert-triangle` - Warning triangle
- `--icon-lightbulb` - Tip lightbulb
- `--icon-target` - Objectives target
- `--icon-check` - Simple checkmark
- `--icon-rocket` - Next steps
- `--icon-clock` - Duration
- `--icon-chevron-right` - Navigation

---

## API / Interface

### HTML Component API

#### Header

```html
<div class="nb-header">
  <span class="nb-header__type">E2E Test</span>
  <h1 class="nb-header__title">Notebook Title</h1>
  <p class="nb-header__subtitle">Brief description</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">5 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags">
    <span class="nb-header__tag">Tag1</span>
  </div>
</div>
```

**Type Badge Values:** `E2E Test` | `Tutorial` | `Reference` | `Algorithm`

**Difficulty Variants:** `--beginner` | `--intermediate` | `--advanced`

#### Callout (with Screen Reader Support)

```html
<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Title</div>
    <div class="nb-callout__body">Body text</div>
  </div>
</div>
```

**Variants:** `--info` | `--success` | `--warning` | `--tip`

#### Section

```html
<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Section Title</h2>
    <p class="nb-section__description">Optional description</p>
  </div>
</div>
```

---

## Error Handling

### CSS Not Loading

**Symptoms:** Notebooks appear unstyled (raw HTML visible)

**Cause:** JupyterHub `custom.js` not mounted correctly

**Resolution:**
1. Check JupyterHub Helm values for `extraFiles` configuration
2. Verify `custom.js` is mounted at `/home/jovyan/.jupyter/lab/static/custom/custom.js`
3. Check browser DevTools Network tab for CSS load failures

### Icon Not Displaying

**Symptoms:** Empty space where icon should appear

**Cause:** CSS mask not supported or icon variable undefined

**Resolution:**
1. Verify `--icon-*` variable is defined in `:root`
2. Check browser supports CSS `mask-image` (all modern browsers do)
3. Ensure `background-color: currentColor` is set on icon element

---

## Anti-Patterns

### Architectural

See [architectural.guardrails.md](--/foundation/architectural.guardrails.md) for the authoritative list.

### Component-Specific

| Anti-Pattern | Correct Approach |
|--------------|------------------|
| Inline `<style>` tags | Use global CSS |
| Emoji for icons | Use CSS mask icons |
| `display(HTML(...))` | Use markdown cells |
| Hardcoded colors | Use `--nb-*` tokens |
| Custom one-off styles | Extend design system |
| Non-sequential section numbers | Keep 1, 2, 3... order |
| Missing `nb-sr-only` in callouts | Include for accessibility |

---

## Testing

### Visual Testing

1. Deploy JupyterHub with CSS configuration
2. Open notebooks in JupyterLab
3. Run Playwright screenshot script:

```bash
cd tools/local-dev && make screenshots
```

4. Review screenshots in `tests/e2e/screenshots/`

### Accessibility Testing

1. **Keyboard navigation**: Tab through all interactive elements
2. **Screen reader**: Test with VoiceOver (macOS) or NVDA (Windows)
3. **Color contrast**: Use browser DevTools accessibility panel
4. **Reduced motion**: Test with `prefers-reduced-motion: reduce`

---

## File Locations

| File | Purpose |
|------|---------|
| `packages/graph-olap-sdk/src/graph_olap/styles/notebook.css` | Single source of truth for CSS (SDK embedded) |
| `infrastructure/helm/charts/jupyterhub/values.yaml` | Init container configuration |
| `docs/standards/notebook-design-system.md` | This document (design specification) |

---

## Research Sources

Design system informed by:

- [Airbnb Design Language System](https://karrisaarinen.com/dls/)
- [Airbnb's Design Principles](https://principles.design/examples/airbnb-design-principles)
- [5 Tips from an Airbnb Designer](https://www.designsystems.com/5-tips-from-an-airbnb-designer-on-maintaining-a-design-system/)
- [Building a Visual Language - Airbnb Design](https://medium.com/airbnb-design/building-a-visual-language-behind-the-scenes-of-our-airbnb-design-system-224748775e4e)
- [Case Study: Airbnb's Design System](https://addictaco.com/case-study-how-airbnbs-design-system-improved-their-ux/)
- [Lucide Icons](https://lucide.dev/) - MIT licensed icon library

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Added Airbnb DLS review, type badge, difficulty indicator, progress, cards |
| 2026-01-13 | Initial design system with CSS mask icons |
