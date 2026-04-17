"""Post-build rewrite to make dist/ openable from file:// URLs.

The astro-relative-links plugin converts absolute asset paths to relative ones,
but internal directory-style links (href="foo/") still depend on the browser
auto-resolving index.html inside a directory — which Safari and Firefox do not
do for file:// URLs. This script appends "index.html" to every internal
directory-style href so double-clicking the landing page yields a fully
navigable offline site.

Run automatically via the `postbuild` npm script.
"""
from __future__ import annotations

import re
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"

# Match href/src/action/data where the value ends in "/" or "/#anchor".
# Skip external URLs (http(s)://, //, mailto:, tel:, data:, javascript:).
# Skip pure "./" or "../" or "../../" etc. (parent/self refs — also handles "../").
DIR_HREF = re.compile(
    r'''(\s(?:href|src|action|data)\s*=\s*["'])'''       # 1: attr opener
    r'''(?!https?:|//|mailto:|tel:|data:|javascript:|#)''' # skip externals/anchors-only
    r'''([^"'#?]*?/)'''                                    # 2: path ending in /
    r'''(#[^"']*)?'''                                      # 3: optional #fragment
    r'''(["'])'''                                          # 4: closing quote
)


def rewrite(match: re.Match[str]) -> str:
    """Append index.html to every internal directory-style href.

    Applies to sub-dir refs ("./foo/", "../foo/") and parent-dir refs
    ("./", "../", "../../"). The "Home" link in Starlight's header uses
    the latter form, and it also needs the suffix to resolve under
    file:// in Safari and Firefox (they do not auto-load index.html
    from a directory URL on local disk).
    """
    opener, path, frag, closer = match.group(1), match.group(2), match.group(3) or "", match.group(4)
    return f"{opener}{path}index.html{frag}{closer}"


OFFLINE_MARKER = "<!-- __pagefind_offline_shim__ -->"


def inject_pagefind_shim(text: str, html_path: Path) -> str:
    """Inject the offline Pagefind data + fetch interceptor before </head>.

    The two scripts load the base64 asset map and install a fetch()
    interceptor on window before Starlight's search UI is initialized.
    Must run in the main thread before the worker is spawned so the
    worker-side shim (prepended to pagefind-worker.js) can reuse the
    same patch.
    """
    if OFFLINE_MARKER in text:
        return text
    depth = len(html_path.relative_to(DIST).parts) - 1
    prefix = "../" * depth if depth else "./"
    shim = (
        f"{OFFLINE_MARKER}\n"
        f'<script src="{prefix}pagefind/_offline-data.js"></script>\n'
        f'<script src="{prefix}pagefind/_offline-patch.js"></script>\n'
    )
    return text.replace("</head>", shim + "</head>", 1)


SERVE_TEMPLATES = Path(__file__).resolve().parent / "serve-templates"


def copy_serve_helpers() -> int:
    """Copy the serve.command / serve.bat / HOW-TO-VIEW.txt helpers into dist.

    These let recipients double-click to start a local HTTP server, which is
    the only reliable way to view the site in Chrome (which blocks ES module
    imports from file:// URLs). Safari and Firefox users can still open
    index.html directly.
    """
    if not SERVE_TEMPLATES.is_dir():
        return 0
    copied = 0
    for src in SERVE_TEMPLATES.iterdir():
        if not src.is_file():
            continue
        dst = DIST / src.name
        dst.write_bytes(src.read_bytes())
        if src.suffix in ("", ".command", ".sh"):
            dst.chmod(0o755)
        copied += 1
    return copied


def main() -> None:
    if not DIST.is_dir():
        raise SystemExit(f"{DIST} not found — run `astro build` first")
    html_files = list(DIST.rglob("*.html"))
    href_changed = 0
    shim_injected = 0
    for html in html_files:
        text = html.read_text(encoding="utf-8")
        new = DIR_HREF.sub(rewrite, text)
        if new != text:
            href_changed += 1
        new2 = inject_pagefind_shim(new, html)
        if new2 != new:
            shim_injected += 1
        if new2 != text:
            html.write_text(new2, encoding="utf-8")
    helpers_copied = copy_serve_helpers()
    print(
        f"offline-fixup: rewrote hrefs in {href_changed}/{len(html_files)} files, "
        f"injected pagefind shim in {shim_injected}/{len(html_files)} files, "
        f"copied {helpers_copied} serve helpers"
    )


if __name__ == "__main__":
    main()
