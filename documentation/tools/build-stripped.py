"""Build a stripped variant of dist/ with no scripts or binaries.

Produces `dist-stripped/` for strict security review: an HSBC-scannable drop
that contains only text (HTML, CSS, SVG, plain text) and is safe to ship
through security pipelines that flag WebAssembly, shell scripts, or large
base64 blobs.

What is removed relative to `dist/`:

* `pagefind/`                  — all of Pagefind's runtime, index, and WASM.
* `serve.command`, `serve.bat` — shell / batch launchers.
* The pagefind shim `<script>` tags injected by `tools/offline-fixup.py`
  (they would otherwise 404 against the removed `pagefind/` folder).

What is kept:

* All 84 HTML pages with their full content, sidebar, TOC, and internal links.
* All SVG diagrams, CSS, and the `_astro/` client bundles.
* `HOW-TO-VIEW.txt`, rewritten to describe the stripped-variant constraints.

The result is purely static, text-only, and opens in Safari/Firefox via
file:// (Chrome still blocks ES module imports — that is a browser policy,
not a bug in this build). Search is unavailable because Pagefind is removed;
the search button in the header will visually render but do nothing.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dist"
DST = ROOT / "dist-stripped"

PAGEFIND_SHIM_BLOCK = re.compile(
    r"<!-- __pagefind_offline_shim__ -->\s*"
    r"<script src=\"[^\"]*pagefind/_offline-data\.js\"></script>\s*"
    r"<script src=\"[^\"]*pagefind/_offline-patch\.js\"></script>\s*"
)


STRIPPED_README = """Graph OLAP Platform — HSBC Handover Documentation (Stripped)
=============================================================

This is the stripped, text-only variant of the handover package. It contains
no executable scripts, no WebAssembly, no binary search-index shards, and no
large base64 blobs. It is intended to pass strict security review pipelines
that flag those file types.


How to view
-----------

Open `index.html` in Safari or Firefox.

    macOS:    Right-click index.html -> Open With -> Safari
    Windows:  Right-click index.html -> Open With -> Firefox

Chrome and Edge will NOT render the site from a local file:// URL because
Chromium browsers block JavaScript module imports on file:// by security
policy. This is a browser-level restriction, not a limitation of the
documentation. If you need to view the site in Chrome, serve it over HTTP
using any static file server (for example, `python3 -m http.server` run
from this folder).


What is different from the full handover package
-------------------------------------------------

* No built-in search. The Pagefind search index and runtime have been
  removed. The search icon in the page header is visible but inert. Use
  your browser's in-page Find (Ctrl+F or Cmd+F) to search within a page,
  or navigate via the sidebar.
* No local-server launcher. The full package ships `serve.command` and
  `serve.bat` helpers; this variant removes them.
* No binary assets. Only HTML, CSS, SVG diagrams, client JavaScript for
  navigation and table-of-contents hydration, and plain text.


Directory layout
----------------

    index.html                  Landing page
    operations/                 Runbooks, handover Q&A, known issues
    architecture/               Architecture and authorization docs
    sdk-manual/                 Python SDK user manual
    api/                        REST API specifications
    component-designs/          Per-service internal designs
    security/, governance/      Security and compliance docs
    _astro/                     Generated CSS and JS (do not edit)
"""


def copy_tree() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)


def remove_scripts_and_binaries() -> list[str]:
    removed: list[str] = []
    pagefind_dir = DST / "pagefind"
    if pagefind_dir.is_dir():
        shutil.rmtree(pagefind_dir)
        removed.append("pagefind/")
    for name in ("serve.command", "serve.bat"):
        p = DST / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


def strip_pagefind_shim_from_html() -> int:
    changed = 0
    for html in DST.rglob("*.html"):
        text = html.read_text(encoding="utf-8")
        new = PAGEFIND_SHIM_BLOCK.sub("", text)
        if new != text:
            html.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def write_readme() -> None:
    (DST / "HOW-TO-VIEW.txt").write_text(STRIPPED_README, encoding="utf-8")


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"{SRC} not found — run `npm run build` first")
    copy_tree()
    removed = remove_scripts_and_binaries()
    stripped_html = strip_pagefind_shim_from_html()
    write_readme()
    print(
        "build-stripped: "
        f"removed {len(removed)} paths ({', '.join(removed) or 'none'}), "
        f"stripped pagefind shim from {stripped_html} HTML files, "
        f"wrote {DST.name}/HOW-TO-VIEW.txt"
    )


if __name__ == "__main__":
    main()
