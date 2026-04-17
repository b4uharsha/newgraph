"""Notebook styling utilities for E2E test notebooks.

Design System based on:
- Airbnb DLS principles (semantic tokens, consistent components)
- WCAG AA accessibility compliance
- Cagle color palette for semantic meaning

Components:
- header(): Gradient header with metadata
- section(): Numbered section headers
- callout(): Unified callout with variants (info, success, warning, tip)
- objectives(): Learning objectives list
- api_ref(): API reference card
- figure(): Image with caption
- details(): Collapsible section
- takeaways(): Key takeaways checklist
"""

from IPython.display import HTML, display
from typing import Optional


# =============================================================================
# DESIGN TOKENS (CSS Custom Properties)
# =============================================================================

NOTEBOOK_CSS = """
<style>
/* === DESIGN TOKENS === */
:root {
  /* Surface colors */
  --nb-surface-primary: #ffffff;
  --nb-surface-muted: #f8fafc;
  --nb-surface-emphasis: linear-gradient(135deg, #3b82f6, #6366f1);

  /* Text colors */
  --nb-text-primary: #1e293b;
  --nb-text-secondary: #64748b;
  --nb-text-muted: #94a3b8;
  --nb-text-inverse: #ffffff;

  /* Border colors */
  --nb-border-default: #e2e8f0;
  --nb-border-emphasis: #3b82f6;

  /* Info (blue) */
  --nb-info-surface: #eff6ff;
  --nb-info-text: #1e40af;
  --nb-info-border: #bfdbfe;
  --nb-info-icon: #3b82f6;

  /* Success (green) */
  --nb-success-surface: #f0fdf4;
  --nb-success-text: #166534;
  --nb-success-border: #bbf7d0;
  --nb-success-icon: #22c55e;

  /* Warning (yellow/amber) */
  --nb-warning-surface: #fffbeb;
  --nb-warning-text: #92400e;
  --nb-warning-border: #fde68a;
  --nb-warning-icon: #f59e0b;

  /* Tip (teal) */
  --nb-tip-surface: #f0fdfa;
  --nb-tip-text: #115e59;
  --nb-tip-border: #99f6e4;
  --nb-tip-icon: #14b8a6;

  /* Typography scale (1.25 ratio) */
  --nb-text-xs: 0.75rem;
  --nb-text-sm: 0.875rem;
  --nb-text-base: 1rem;
  --nb-text-lg: 1.125rem;
  --nb-text-xl: 1.25rem;
  --nb-text-2xl: 1.5rem;
  --nb-text-3xl: 1.875rem;

  /* Spacing scale (4px base) */
  --nb-space-1: 0.25rem;
  --nb-space-2: 0.5rem;
  --nb-space-3: 0.75rem;
  --nb-space-4: 1rem;
  --nb-space-6: 1.5rem;
  --nb-space-8: 2rem;

  /* Border radius */
  --nb-radius-sm: 0.25rem;
  --nb-radius-md: 0.5rem;
  --nb-radius-lg: 0.75rem;
  --nb-radius-full: 9999px;

  /* Shadows */
  --nb-shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --nb-shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1);
}

/* === COMPONENT STYLES === */

/* Notebook Header */
.nb-header {
  background: var(--nb-surface-emphasis);
  color: var(--nb-text-inverse);
  padding: var(--nb-space-8);
  border-radius: var(--nb-radius-lg);
  margin-bottom: var(--nb-space-6);
  box-shadow: var(--nb-shadow-md);
}

.nb-header__title {
  font-size: var(--nb-text-3xl);
  font-weight: 700;
  margin: 0 0 var(--nb-space-2) 0;
  line-height: 1.2;
}

.nb-header__subtitle {
  font-size: var(--nb-text-lg);
  opacity: 0.9;
  margin: 0 0 var(--nb-space-4) 0;
}

.nb-header__meta {
  display: flex;
  gap: var(--nb-space-4);
  flex-wrap: wrap;
  font-size: var(--nb-text-sm);
  opacity: 0.85;
}

.nb-header__tags {
  display: flex;
  gap: var(--nb-space-2);
  flex-wrap: wrap;
  margin-top: var(--nb-space-3);
}

.nb-header__tag {
  background: rgba(255,255,255,0.2);
  padding: var(--nb-space-1) var(--nb-space-3);
  border-radius: var(--nb-radius-full);
  font-size: var(--nb-text-xs);
  font-weight: 500;
}

/* Section Header */
.nb-section {
  display: flex;
  align-items: baseline;
  gap: var(--nb-space-3);
  margin: var(--nb-space-8) 0 var(--nb-space-4) 0;
  padding-bottom: var(--nb-space-2);
  border-bottom: 2px solid var(--nb-border-default);
}

.nb-section__number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  background: var(--nb-surface-emphasis);
  color: var(--nb-text-inverse);
  border-radius: var(--nb-radius-full);
  font-size: var(--nb-text-sm);
  font-weight: 600;
  flex-shrink: 0;
}

.nb-section__title {
  font-size: var(--nb-text-2xl);
  font-weight: 600;
  color: var(--nb-text-primary);
  margin: 0;
}

.nb-section__description {
  font-size: var(--nb-text-base);
  color: var(--nb-text-secondary);
  margin-top: var(--nb-space-1);
}

/* Unified Callout */
.nb-callout {
  display: flex;
  gap: var(--nb-space-3);
  padding: var(--nb-space-4);
  border-radius: var(--nb-radius-md);
  border: 1px solid;
  margin: var(--nb-space-4) 0;
}

.nb-callout__icon {
  font-size: var(--nb-text-xl);
  flex-shrink: 0;
  line-height: 1;
}

.nb-callout__content {
  flex: 1;
  min-width: 0;
}

.nb-callout__title {
  font-weight: 600;
  margin-bottom: var(--nb-space-1);
}

.nb-callout__body {
  font-size: var(--nb-text-sm);
  line-height: 1.5;
}

.nb-callout--info {
  background: var(--nb-info-surface);
  border-color: var(--nb-info-border);
  color: var(--nb-info-text);
}

.nb-callout--success {
  background: var(--nb-success-surface);
  border-color: var(--nb-success-border);
  color: var(--nb-success-text);
}

.nb-callout--warning {
  background: var(--nb-warning-surface);
  border-color: var(--nb-warning-border);
  color: var(--nb-warning-text);
}

.nb-callout--tip {
  background: var(--nb-tip-surface);
  border-color: var(--nb-tip-border);
  color: var(--nb-tip-text);
}

/* Objectives */
.nb-objectives {
  background: var(--nb-surface-muted);
  border-radius: var(--nb-radius-md);
  padding: var(--nb-space-4) var(--nb-space-6);
  margin: var(--nb-space-4) 0;
}

.nb-objectives__title {
  font-size: var(--nb-text-lg);
  font-weight: 600;
  color: var(--nb-text-primary);
  margin: 0 0 var(--nb-space-3) 0;
  display: flex;
  align-items: center;
  gap: var(--nb-space-2);
}

.nb-objectives__list {
  margin: 0;
  padding-left: var(--nb-space-6);
  color: var(--nb-text-secondary);
}

.nb-objectives__list li {
  margin-bottom: var(--nb-space-2);
  line-height: 1.5;
}

.nb-objectives__list li:last-child {
  margin-bottom: 0;
}

/* API Reference */
.nb-api-ref {
  background: var(--nb-surface-primary);
  border: 1px solid var(--nb-border-default);
  border-radius: var(--nb-radius-md);
  margin: var(--nb-space-4) 0;
  overflow: hidden;
}

.nb-api-ref__header {
  background: var(--nb-surface-muted);
  padding: var(--nb-space-3) var(--nb-space-4);
  border-bottom: 1px solid var(--nb-border-default);
}

.nb-api-ref__signature {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: var(--nb-text-sm);
  color: var(--nb-text-primary);
  margin: 0;
  word-break: break-word;
}

.nb-api-ref__body {
  padding: var(--nb-space-4);
}

.nb-api-ref__description {
  color: var(--nb-text-secondary);
  margin-bottom: var(--nb-space-4);
  line-height: 1.5;
}

.nb-api-ref__section {
  margin-bottom: var(--nb-space-3);
}

.nb-api-ref__section:last-child {
  margin-bottom: 0;
}

.nb-api-ref__section-title {
  font-size: var(--nb-text-sm);
  font-weight: 600;
  color: var(--nb-text-primary);
  margin-bottom: var(--nb-space-2);
}

.nb-api-ref__params {
  font-size: var(--nb-text-sm);
  color: var(--nb-text-secondary);
  margin: 0;
  padding-left: var(--nb-space-4);
}

.nb-api-ref__params li {
  margin-bottom: var(--nb-space-1);
}

.nb-api-ref__param-name {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  color: var(--nb-info-text);
}

.nb-api-ref__returns {
  font-size: var(--nb-text-sm);
  color: var(--nb-text-secondary);
}

/* Figure */
.nb-figure {
  margin: var(--nb-space-6) 0;
  text-align: center;
}

.nb-figure__img {
  max-width: 100%;
  height: auto;
  border-radius: var(--nb-radius-md);
  box-shadow: var(--nb-shadow-sm);
}

.nb-figure__caption {
  margin-top: var(--nb-space-2);
  font-size: var(--nb-text-sm);
  color: var(--nb-text-muted);
  font-style: italic;
}

/* Details (Collapsible) */
.nb-details {
  background: var(--nb-surface-muted);
  border-radius: var(--nb-radius-md);
  margin: var(--nb-space-4) 0;
  overflow: hidden;
}

.nb-details summary {
  padding: var(--nb-space-3) var(--nb-space-4);
  cursor: pointer;
  font-weight: 600;
  color: var(--nb-text-primary);
  display: flex;
  align-items: center;
  gap: var(--nb-space-2);
  min-height: 44px; /* WCAG touch target */
  user-select: none;
}

.nb-details summary:focus-visible {
  outline: 2px solid var(--nb-border-emphasis);
  outline-offset: -2px;
}

.nb-details summary:hover {
  background: rgba(0,0,0,0.03);
}

.nb-details summary::before {
  content: "▶";
  font-size: var(--nb-text-xs);
  transition: transform 0.2s ease;
}

.nb-details[open] summary::before {
  transform: rotate(90deg);
}

.nb-details__content {
  padding: 0 var(--nb-space-4) var(--nb-space-4) var(--nb-space-4);
  color: var(--nb-text-secondary);
  line-height: 1.6;
}

/* Takeaways */
.nb-takeaways {
  background: var(--nb-success-surface);
  border: 1px solid var(--nb-success-border);
  border-radius: var(--nb-radius-md);
  padding: var(--nb-space-4) var(--nb-space-6);
  margin: var(--nb-space-6) 0;
}

.nb-takeaways__title {
  font-size: var(--nb-text-lg);
  font-weight: 600;
  color: var(--nb-success-text);
  margin: 0 0 var(--nb-space-3) 0;
  display: flex;
  align-items: center;
  gap: var(--nb-space-2);
}

.nb-takeaways__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.nb-takeaways__list li {
  padding-left: var(--nb-space-6);
  position: relative;
  margin-bottom: var(--nb-space-2);
  color: var(--nb-success-text);
  line-height: 1.5;
}

.nb-takeaways__list li::before {
  content: "✓";
  position: absolute;
  left: 0;
  color: var(--nb-success-icon);
  font-weight: bold;
}

.nb-takeaways__list li:last-child {
  margin-bottom: 0;
}

/* Badge */
.nb-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--nb-space-1) var(--nb-space-3);
  border-radius: var(--nb-radius-full);
  font-size: var(--nb-text-xs);
  font-weight: 500;
}

.nb-badge--blue {
  background: var(--nb-info-surface);
  color: var(--nb-info-text);
}

.nb-badge--green {
  background: var(--nb-success-surface);
  color: var(--nb-success-text);
}

.nb-badge--yellow {
  background: var(--nb-warning-surface);
  color: var(--nb-warning-text);
}

.nb-badge--red {
  background: #fef2f2;
  color: #991b1b;
}

.nb-badge--gray {
  background: #f3f4f6;
  color: #374151;
}

.nb-badge--purple {
  background: #f5f3ff;
  color: #5b21b6;
}

/* Code Block */
.nb-code {
  background: var(--nb-surface-muted);
  border: 1px solid var(--nb-border-default);
  border-radius: var(--nb-radius-md);
  padding: var(--nb-space-4);
  margin: var(--nb-space-4) 0;
  overflow-x: auto;
}

.nb-code pre {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: var(--nb-text-sm);
  line-height: 1.5;
  color: var(--nb-text-primary);
}

/* Step Indicator */
.nb-steps {
  display: flex;
  gap: var(--nb-space-2);
  margin: var(--nb-space-4) 0;
  flex-wrap: wrap;
}

.nb-step {
  display: flex;
  align-items: center;
  gap: var(--nb-space-2);
  padding: var(--nb-space-2) var(--nb-space-3);
  border-radius: var(--nb-radius-md);
  font-size: var(--nb-text-sm);
  background: var(--nb-surface-muted);
  color: var(--nb-text-secondary);
}

.nb-step--current {
  background: var(--nb-info-surface);
  color: var(--nb-info-text);
  font-weight: 600;
}

.nb-step--completed {
  background: var(--nb-success-surface);
  color: var(--nb-success-text);
}

.nb-step__number {
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--nb-radius-full);
  background: currentColor;
  color: white;
  font-size: var(--nb-text-xs);
  font-weight: 600;
}

.nb-step--current .nb-step__number,
.nb-step--completed .nb-step__number {
  background: currentColor;
}

/* Reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  .nb-details summary::before {
    transition: none;
  }
}

/* =============================================================================
   OUTPUT CELL STYLING - Tame Jupyter's default error output
   ============================================================================= */

/* Reduce visual weight of ANSI-colored error backgrounds */
.ansi-yellow-bg {
  background-color: #fef9e7 !important;  /* Much softer yellow */
}

.ansi-red-bg {
  background-color: #fef2f2 !important;  /* Soft red */
}

/* Soften red text in errors - make it amber instead */
.ansi-red-fg {
  color: #b45309 !important;  /* Amber instead of harsh red */
}

/* Style the output area containing errors */
.jp-OutputArea-output:has(.ansi-yellow-bg),
.jp-OutputArea-output:has(.ansi-red-fg) {
  max-height: 250px;
  overflow-y: auto;
  border-radius: var(--nb-radius-md, 0.5rem);
  margin: var(--nb-space-2, 0.5rem) 0;
}

/* Add a subtle border to text outputs */
.jp-RenderedText.jp-OutputArea-output {
  border-left: 3px solid var(--nb-border-default, #e2e8f0);
  padding-left: var(--nb-space-3, 0.75rem);
  font-size: 0.8rem;
  line-height: 1.4;
}

/* Reduce prominence of traceback text */
.jp-RenderedText pre {
  font-size: 0.75rem !important;
  opacity: 0.85;
}

/* Make the overall output area more compact */
.jp-Cell-outputWrapper {
  margin-top: var(--nb-space-2, 0.5rem);
}

/* CRITICAL: Collapse error output to max 3 lines with scroll */
.jp-RenderedText.jp-OutputArea-output {
  background: #f8fafc;
  border-radius: 6px;
  padding: 8px 12px !important;
  margin: 4px 0;
  border: 1px solid #e2e8f0;
}

/* Target the pre element inside to limit height */
.jp-RenderedText.jp-OutputArea-output pre {
  max-height: 100px !important;
  overflow-y: auto !important;
  margin: 0 !important;
}

/* When there's lots of output children, make each compact */
.jp-OutputArea-child {
  margin-bottom: 4px;
}

/* Style the scrollbar */
.jp-RenderedText.jp-OutputArea-output::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.jp-RenderedText.jp-OutputArea-output::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

/* Add a fade effect at the bottom to indicate more content */
.jp-RenderedText.jp-OutputArea-output::after {
  content: "";
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  height: 20px;
  background: linear-gradient(transparent, #f8fafc);
  pointer-events: none;
}

/* Test Result Styling */
.nb-test-result {
  display: flex;
  align-items: center;
  gap: var(--nb-space-3);
  padding: var(--nb-space-3) var(--nb-space-4);
  border-radius: var(--nb-radius-md);
  margin: var(--nb-space-2) 0;
  font-weight: 500;
}

.nb-test-result--pass {
  background: var(--nb-success-surface);
  color: var(--nb-success-text);
  border: 1px solid var(--nb-success-border);
}

.nb-test-result--fail {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.nb-test-result--skip {
  background: var(--nb-surface-muted);
  color: var(--nb-text-secondary);
  border: 1px solid var(--nb-border-default);
}

/* Infrastructure Required Card */
.nb-infra-required {
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border: 1px solid #f59e0b;
  border-radius: var(--nb-radius-lg);
  padding: var(--nb-space-6);
  margin: var(--nb-space-4) 0;
  text-align: center;
}

.nb-infra-required__icon {
  font-size: 2rem;
  margin-bottom: var(--nb-space-2);
}

.nb-infra-required__title {
  font-size: var(--nb-text-lg);
  font-weight: 600;
  color: #92400e;
  margin-bottom: var(--nb-space-2);
}

.nb-infra-required__message {
  color: #a16207;
  font-size: var(--nb-text-sm);
}

/* Output Summary Card */
.nb-output-summary {
  background: var(--nb-surface-muted);
  border-radius: var(--nb-radius-md);
  padding: var(--nb-space-4);
  margin: var(--nb-space-4) 0;
  border: 1px solid var(--nb-border-default);
}

.nb-output-summary__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--nb-space-3);
}

.nb-output-summary__title {
  font-weight: 600;
  color: var(--nb-text-primary);
}

.nb-output-summary__stats {
  display: flex;
  gap: var(--nb-space-4);
  font-size: var(--nb-text-sm);
}

.nb-output-summary__stat {
  display: flex;
  align-items: center;
  gap: var(--nb-space-1);
}

.nb-output-summary__stat--pass { color: var(--nb-success-text); }
.nb-output-summary__stat--fail { color: #991b1b; }
.nb-output-summary__stat--skip { color: var(--nb-text-muted); }
</style>
"""

_styles_injected = False


def init_styles() -> HTML:
    """Inject CSS design tokens and styling functions into the notebook.

    Call this once at the start of a notebook to enable all styling.
    Safe to call multiple times (idempotent).

    This function also injects commonly-used styling functions into the
    IPython global namespace so they can be called without explicit imports.

    Returns:
        HTML object that injects the CSS when displayed
    """
    global _styles_injected
    if _styles_injected:
        return HTML("")
    _styles_injected = True

    # Inject styling functions into IPython's user namespace
    try:
        from IPython import get_ipython
        ip = get_ipython()
        if ip is not None:
            # Get functions from this module's globals
            import sys
            ns = sys.modules[__name__]
            # Inject commonly-used functions
            ip.user_ns['styled_table'] = ns.styled_table
            ip.user_ns['callout'] = ns.callout
            ip.user_ns['section'] = ns.section
            ip.user_ns['header'] = ns.header
            ip.user_ns['objectives'] = ns.objectives
            ip.user_ns['api_ref'] = ns.api_ref
            ip.user_ns['figure'] = ns.figure
            ip.user_ns['details'] = ns.details
            ip.user_ns['takeaways'] = ns.takeaways
            ip.user_ns['badge'] = ns.badge
            ip.user_ns['code_block'] = ns.code_block
            ip.user_ns['step_indicator'] = ns.step_indicator
            ip.user_ns['test_result'] = ns.test_result
            ip.user_ns['infra_required'] = ns.infra_required
            ip.user_ns['comparison_table'] = ns.comparison_table
            ip.user_ns['info_box'] = ns.info_box
            ip.user_ns['success_box'] = ns.success_box
            ip.user_ns['warning_box'] = ns.warning_box
            ip.user_ns['tip_box'] = ns.tip_box
            ip.user_ns['notebook_header'] = ns.notebook_header
            ip.user_ns['section_header'] = ns.section_header
            ip.user_ns['collapsible'] = ns.collapsible
            ip.user_ns['concept_card'] = ns.concept_card
            ip.user_ns['key_takeaways'] = ns.key_takeaways
            ip.user_ns['next_steps'] = ns.next_steps
    except Exception:
        pass  # Silently fail if not in IPython environment

    return HTML(NOTEBOOK_CSS)


# =============================================================================
# CORE COMPONENTS (8 functions)
# =============================================================================

def header(
    title: str,
    subtitle: str,
    duration: str = "",
    level: str = "",
    tags: Optional[list[str]] = None
) -> HTML:
    """Create a gradient header for the notebook.

    Args:
        title: Main notebook title
        subtitle: Brief description
        duration: Estimated time (e.g., "15 min")
        level: Difficulty level (e.g., "Beginner", "Intermediate")
        tags: List of topic tags

    Returns:
        HTML object for display
    """
    meta_items = []
    if duration:
        meta_items.append(f"<span>⏱️ {duration}</span>")
    if level:
        meta_items.append(f"<span>📊 {level}</span>")

    meta_html = f'<div class="nb-header__meta">{" ".join(meta_items)}</div>' if meta_items else ""

    tags_html = ""
    if tags:
        tag_spans = "".join(f'<span class="nb-header__tag">{tag}</span>' for tag in tags)
        tags_html = f'<div class="nb-header__tags">{tag_spans}</div>'

    return HTML(f'''<div class="nb-header">
  <h1 class="nb-header__title">{title}</h1>
  <p class="nb-header__subtitle">{subtitle}</p>
  {meta_html}
  {tags_html}
</div>''')


def section(number: int, title: str, description: str = "") -> HTML:
    """Create a numbered section header.

    Args:
        number: Section number (displayed in circle)
        title: Section title
        description: Optional description text

    Returns:
        HTML object for display
    """
    desc_html = f'<p class="nb-section__description">{description}</p>' if description else ""

    return HTML(f'''<div class="nb-section">
  <span class="nb-section__number">{number}</span>
  <div>
    <h2 class="nb-section__title">{title}</h2>
    {desc_html}
  </div>
</div>''')


def callout(title: str, content: str = "", variant: str = "info") -> HTML:
    """Create a callout box with icon.

    Args:
        title: Callout title
        content: Callout body text (can contain HTML)
        variant: One of 'info', 'success', 'warning', 'tip'

    Returns:
        HTML object for display
    """
    icons = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "tip": "💡",
    }
    icon = icons.get(variant, icons["info"])
    variant_class = f"nb-callout--{variant}" if variant in icons else "nb-callout--info"

    body_html = f'<div class="nb-callout__body">{content}</div>' if content else ""

    return HTML(f'''<div class="nb-callout {variant_class}">
  <span class="nb-callout__icon">{icon}</span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">{title}</div>
    {body_html}
  </div>
</div>''')


def objectives(items: list[str], title: str = "What You'll Learn") -> HTML:
    """Create a learning objectives box.

    Args:
        items: List of learning objectives
        title: Box title

    Returns:
        HTML object for display
    """
    list_items = "".join(f"<li>{item}</li>" for item in items)

    return HTML(f'''<div class="nb-objectives">
  <h3 class="nb-objectives__title">🎯 {title}</h3>
  <ul class="nb-objectives__list">
    {list_items}
  </ul>
</div>''')


def api_ref(
    signature: str,
    description: str,
    params: Optional[dict[str, str]] = None,
    returns: str = ""
) -> HTML:
    """Create an API reference card.

    Args:
        signature: Function/method signature (e.g., "client.health.check()")
        description: What the function does
        params: Dictionary of parameter name -> description
        returns: Return value description

    Returns:
        HTML object for display
    """
    params_html = ""
    if params:
        param_items = "".join(
            f'<li><span class="nb-api-ref__param-name">{name}</span>: {desc}</li>'
            for name, desc in params.items()
        )
        params_html = f'''<div class="nb-api-ref__section">
      <div class="nb-api-ref__section-title">Parameters</div>
      <ul class="nb-api-ref__params">{param_items}</ul>
    </div>'''

    returns_html = ""
    if returns:
        returns_html = f'''<div class="nb-api-ref__section">
      <div class="nb-api-ref__section-title">Returns</div>
      <p class="nb-api-ref__returns">{returns}</p>
    </div>'''

    return HTML(f'''<div class="nb-api-ref">
  <div class="nb-api-ref__header">
    <code class="nb-api-ref__signature">{signature}</code>
  </div>
  <div class="nb-api-ref__body">
    <p class="nb-api-ref__description">{description}</p>
    {params_html}
    {returns_html}
  </div>
</div>''')


def figure(src: str, alt: str, caption: str = "") -> HTML:
    """Create an image with optional caption.

    Args:
        src: Image source path/URL
        alt: Alt text for accessibility
        caption: Optional caption text

    Returns:
        HTML object for display
    """
    caption_html = f'<figcaption class="nb-figure__caption">{caption}</figcaption>' if caption else ""

    return HTML(f'''<figure class="nb-figure">
  <img class="nb-figure__img" src="{src}" alt="{alt}">
  {caption_html}
</figure>''')


def details(summary: str, content: str, open_by_default: bool = False) -> HTML:
    """Create a collapsible section.

    Args:
        summary: The clickable summary text
        content: The expandable content (can contain HTML)
        open_by_default: Whether to start expanded

    Returns:
        HTML object for display
    """
    open_attr = " open" if open_by_default else ""

    return HTML(f'''<details class="nb-details"{open_attr}>
  <summary>{summary}</summary>
  <div class="nb-details__content">
    {content}
  </div>
</details>''')


def takeaways(items: list[str], title: str = "Key Takeaways") -> HTML:
    """Create a key takeaways checklist.

    Args:
        items: List of takeaway points
        title: Box title

    Returns:
        HTML object for display
    """
    list_items = "".join(f"<li>{item}</li>" for item in items)

    return HTML(f'''<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">✅ {title}</h3>
  <ul class="nb-takeaways__list">
    {list_items}
  </ul>
</div>''')


# =============================================================================
# UTILITY COMPONENTS
# =============================================================================

def badge(text: str, color: str = "blue") -> HTML:
    """Create a colored badge/tag.

    Args:
        text: The badge text
        color: Color name (blue, green, yellow, red, gray, purple)

    Returns:
        HTML object for display
    """
    return HTML(f'<span class="nb-badge nb-badge--{color}">{text}</span>')


def code_block(code: str, language: str = "python") -> HTML:
    """Create a styled code block.

    Args:
        code: The code to display
        language: Programming language (for future syntax highlighting)

    Returns:
        HTML object for display
    """
    # Escape HTML entities in code
    import html
    escaped_code = html.escape(code)
    return HTML(f'<div class="nb-code"><pre>{escaped_code}</pre></div>')


def step_indicator(steps: list[str], current_step: int = 0) -> HTML:
    """Create a step progress indicator.

    Args:
        steps: List of step names
        current_step: 0-indexed current step

    Returns:
        HTML object for display
    """
    step_html = []
    for i, step in enumerate(steps):
        if i < current_step:
            css_class = "nb-step nb-step--completed"
            icon = "✓"
        elif i == current_step:
            css_class = "nb-step nb-step--current"
            icon = str(i + 1)
        else:
            css_class = "nb-step"
            icon = str(i + 1)

        step_html.append(f'''<div class="{css_class}">
      <span class="nb-step__number">{icon}</span>
      <span>{step}</span>
    </div>''')

    return HTML(f'<div class="nb-steps">{"".join(step_html)}</div>')


# =============================================================================
# BACKWARDS COMPATIBILITY ALIASES
# =============================================================================

def notebook_header(
    title: str,
    subtitle: str = "",
    duration: str = "",
    level: str = "",
    tags: Optional[list[str]] = None
) -> HTML:
    """Alias for header() - backwards compatibility."""
    return header(title, subtitle, duration, level, tags)


def section_header(number: int, title: str, description: str = "") -> HTML:
    """Alias for section() - backwards compatibility."""
    return section(number, title, description)


def info_box(title: str, content: str = "") -> HTML:
    """Create a blue info message box. Alias for callout(variant='info')."""
    return callout(title, content, "info")


def success_box(title: str, content: str = "") -> HTML:
    """Create a green success message box. Alias for callout(variant='success')."""
    return callout(title, content, "success")


def warning_box(title: str, content: str = "") -> HTML:
    """Create a yellow warning message box. Alias for callout(variant='warning')."""
    return callout(title, content, "warning")


def tip_box(title: str, content: str = "") -> HTML:
    """Create a teal tip message box. Alias for callout(variant='tip')."""
    return callout(title, content, "tip")


def collapsible(title: str, content: str, open_by_default: bool = False) -> HTML:
    """Alias for details() - backwards compatibility."""
    return details(title, content, open_by_default)


def concept_card(title: str, content: str) -> HTML:
    """Create a concept explanation card. Alias for callout(variant='info')."""
    return callout(title, content, "info")


def learn_more(title: str, content: str) -> HTML:
    """Create a 'learn more' collapsible section."""
    return details(f"📖 {title}", content)


def key_takeaways(items: list[str]) -> HTML:
    """Alias for takeaways() - backwards compatibility."""
    return takeaways(items)


def next_steps(items: list[str]) -> HTML:
    """Create a 'next steps' list."""
    list_items = "".join(f"<li>{item}</li>" for item in items)
    return HTML(f'''<div class="nb-objectives">
  <h3 class="nb-objectives__title">🚀 Next Steps</h3>
  <ul class="nb-objectives__list">
    {list_items}
  </ul>
</div>''')


def image_with_caption(src: str, alt: str, caption: str = "") -> HTML:
    """Alias for figure() - backwards compatibility."""
    return figure(src, alt, caption)


def styled_table(headers: list[str], rows: list[list[str]], title: str = None) -> HTML:
    """Create a styled HTML table.

    Args:
        headers: List of column headers
        rows: List of row data (each row is a list of cell values)
        title: Optional title displayed above the table

    Returns:
        HTML object for display
    """
    header_html = "".join(f"<th>{h}</th>" for h in headers)

    rows_html = ""
    for row in rows:
        cells = "".join(f"<td>{cell}</td>" for cell in row)
        rows_html += f"<tr>{cells}</tr>"

    title_html = f'<h4 style="margin-bottom: 8px; color: var(--nb-text-primary, #1e293b);">{title}</h4>' if title else ""

    return HTML(f'''{title_html}<table style="width:100%; border-collapse:collapse; margin:1rem 0;">
  <thead style="background:var(--nb-surface-muted, #f8fafc);">
    <tr style="border-bottom:2px solid var(--nb-border-default, #e2e8f0);">
      {header_html}
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
<style>
table th, table td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--nb-border-default, #e2e8f0); }}
table tr:hover {{ background: var(--nb-surface-muted, #f8fafc); }}
</style>''')


def comparison_table(headers: list[str], rows: list[list[str]]) -> HTML:
    """Alias for styled_table() - backwards compatibility."""
    return styled_table(headers, rows)


# =============================================================================
# TEST OUTPUT COMPONENTS - For E2E test notebooks
# =============================================================================

def test_result(name: str, status: str = "pass", message: str = "") -> HTML:
    """Display a styled test result.

    Args:
        name: Test name/description
        status: One of 'pass', 'fail', 'skip'
        message: Optional detail message

    Returns:
        HTML object for display
    """
    icons = {"pass": "✓", "fail": "✗", "skip": "○"}
    icon = icons.get(status, icons["pass"])
    status_class = f"nb-test-result--{status}" if status in icons else "nb-test-result--pass"

    msg_html = f'<span style="opacity: 0.8; font-weight: normal;"> — {message}</span>' if message else ""

    return HTML(f'''<div class="nb-test-result {status_class}">
  <span>{icon}</span>
  <span>{name}{msg_html}</span>
</div>''')


def infra_required(
    title: str = "Infrastructure Required",
    message: str = "This notebook requires a running Graph OLAP cluster. Deploy the platform first."
) -> HTML:
    """Display a styled 'infrastructure required' card.

    Use this instead of showing raw connection errors.

    Args:
        title: Card title
        message: Explanation message

    Returns:
        HTML object for display
    """
    return HTML(f'''<div class="nb-infra-required">
  <div class="nb-infra-required__icon">🔌</div>
  <div class="nb-infra-required__title">{title}</div>
  <div class="nb-infra-required__message">{message}</div>
</div>''')


def test_summary(passed: int, failed: int, skipped: int = 0, title: str = "Test Results") -> HTML:
    """Display a test summary card.

    Args:
        passed: Number of passed tests
        failed: Number of failed tests
        skipped: Number of skipped tests
        title: Summary title

    Returns:
        HTML object for display
    """
    total = passed + failed + skipped

    return HTML(f'''<div class="nb-output-summary">
  <div class="nb-output-summary__header">
    <span class="nb-output-summary__title">{title}</span>
    <div class="nb-output-summary__stats">
      <span class="nb-output-summary__stat nb-output-summary__stat--pass">✓ {passed} passed</span>
      <span class="nb-output-summary__stat nb-output-summary__stat--fail">✗ {failed} failed</span>
      {f'<span class="nb-output-summary__stat nb-output-summary__stat--skip">○ {skipped} skipped</span>' if skipped else ''}
    </div>
  </div>
  <div style="background: #e2e8f0; border-radius: 4px; height: 8px; overflow: hidden;">
    <div style="display: flex; height: 100%;">
      <div style="width: {passed/total*100 if total else 0}%; background: #22c55e;"></div>
      <div style="width: {failed/total*100 if total else 0}%; background: #ef4444;"></div>
      <div style="width: {skipped/total*100 if total else 0}%; background: #94a3b8;"></div>
    </div>
  </div>
</div>''')


# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# =============================================================================

# Alias for api_ref -> api_reference
api_reference = api_ref

# Save original styled_table before overriding
_original_styled_table = styled_table

# Alias for styled_table that accepts optional title parameter
def styled_table(headers: list[str], rows: list[list[str]], title: str = None) -> HTML:
    """Backward-compatible styled_table with optional title."""
    result = _original_styled_table(headers, rows)
    if title:
        # Wrap with title if provided
        return HTML(f'<div><h4 style="margin-bottom: 8px;">{title}</h4>{result.data}</div>')
    return result

# method_signature stub (for notebooks that import it)
def method_signature(signature: str, description: str = "") -> HTML:
    """Display a method signature card."""
    return HTML(f'''<div class="nb-api-ref">
  <div class="nb-api-ref__header">
    <code class="nb-api-ref__signature">{signature}</code>
  </div>
  {f'<div class="nb-api-ref__body"><p class="nb-api-ref__description">{description}</p></div>' if description else ''}
</div>''')
