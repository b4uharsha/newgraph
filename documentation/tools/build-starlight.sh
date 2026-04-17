#!/usr/bin/env bash
# build-starlight.sh — Build the Starlight documentation site from handover/ content.
#
# Usage:
#   ./tools/build-starlight.sh              # Full build (copy + inject frontmatter + npm build)
#   ./tools/build-starlight.sh --copy-only  # Copy and inject only (skip npm build)
#
# Prerequisites:
#   - Node.js >= 20
#   - npm dependencies installed (npm ci)
#
# Output:
#   dist/   — Static site ready to serve

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HANDOVER_DIR="${HANDOVER_DIR:-$(cd "$PROJECT_DIR/../.." && pwd)/handover}"
DOCS_DIR="$PROJECT_DIR/src/content/docs"
DIAGRAMS_DIR="$PROJECT_DIR/public/diagrams"

# ── Validate ───────────────────────────────────────────────────────────
if [ ! -d "$HANDOVER_DIR" ]; then
    echo "ERROR: Handover directory not found: $HANDOVER_DIR" >&2
    echo "Set HANDOVER_DIR to override." >&2
    exit 1
fi

echo "==> Source:    $HANDOVER_DIR"
echo "==> Target:    $DOCS_DIR"
echo "==> Diagrams:  $DIAGRAMS_DIR"
echo ""

# ── Step 0: Drift-detection guard (ADR-142) ───────────────────────────
# If the target content tree contains uncommitted changes relative to git HEAD,
# abort loudly instead of silently overwriting them. This is the belt-and-
# suspenders safety net from ADR-142 that catches the case where a developer
# has edited src/content/docs/ directly (treating it as a human-authored tree)
# and is about to lose that work to build-starlight.sh's rebuild. Set
# SKIP_DRIFT_CHECK=1 to bypass (e.g., in CI where the working tree is known
# to be clean by construction or intentionally contains untracked output from
# a prior prebuild step).
if [ -z "${SKIP_DRIFT_CHECK:-}" ] && [ -d "$DOCS_DIR/.." ] && git -C "$DOCS_DIR/.." rev-parse --git-dir >/dev/null 2>&1; then
    rel_docs_dir="$(cd "$DOCS_DIR" && git rev-parse --show-prefix 2>/dev/null || true)"
    if [ -n "$rel_docs_dir" ]; then
        DIRTY=$(git -C "$DOCS_DIR/.." status --porcelain -- "$rel_docs_dir" 2>/dev/null | grep -v '^??' || true)
        if [ -n "$DIRTY" ]; then
            echo "ERROR: build-starlight.sh would overwrite uncommitted changes in" >&2
            echo "  $DOCS_DIR" >&2
            echo "" >&2
            echo "Files with pending changes:" >&2
            echo "$DIRTY" | sed 's|^|  |' >&2
            echo "" >&2
            echo "These files are build artifacts per ADR-142. If you intended to edit" >&2
            echo "them, port the edits to docs/ (monorepo source of truth) and re-run" >&2
            echo "build-starlight.sh instead. To bypass this check (e.g., in CI):" >&2
            echo "  SKIP_DRIFT_CHECK=1 ./tools/build-starlight.sh [--copy-only]" >&2
            exit 1
        fi
    fi
fi

# ── Step 1: Clean target directories ──────────────────────────────────
# Preserve checked-in files (index.mdx, .gitkeep) while removing copied content.
echo "--- Cleaning target directories"
if [ -d "$DOCS_DIR" ]; then
    TMPKEEP=$(mktemp -d)
    for keep in index.mdx .gitkeep; do
        [ -f "$DOCS_DIR/$keep" ] && cp "$DOCS_DIR/$keep" "$TMPKEEP/"
    done
    rm -rf "$DOCS_DIR"
    mkdir -p "$DOCS_DIR"
    for keep in index.mdx .gitkeep; do
        [ -f "$TMPKEEP/$keep" ] && cp "$TMPKEEP/$keep" "$DOCS_DIR/"
    done
    rm -rf "$TMPKEEP"
else
    mkdir -p "$DOCS_DIR"
fi
rm -rf "$DIAGRAMS_DIR"
mkdir -p "$DIAGRAMS_DIR"

# ── Step 2: Copy markdown content (renaming dots to dashes) ───────────
# Astro/Starlight content collection slugs strip dots from filenames,
# producing ugly URLs like /operations/platform-operationsmanual/.
# Rename dots to dashes during copy so slugs become clean:
#   platform-operations.manual.md → platform-operations-manual.md
#   → URL: /operations/platform-operations-manual/
echo "--- Copying markdown content (renaming dots to dashes)"
cd "$HANDOVER_DIR"
find . -name '*.md' \
    ! -name 'document.structure.md' \
    ! -name 'README.md' \
    -print0 | while IFS= read -r -d '' f; do
    rel_dir=$(dirname "$f")
    base=$(basename "$f" .md)
    new_base="${base//./-}"
    target_dir="$DOCS_DIR/$rel_dir"
    mkdir -p "$target_dir"
    cp "$f" "$target_dir/${new_base}.md"
done

# Rewrite cross-reference URLs in copied markdown files:
# any .manual/, .runbook/, .spec/, .design/, .governance/, .reference/ path
# becomes -manual/, -runbook/, -spec/, -design/, -governance/, -reference/
# to match the renamed files.
echo "--- Rewriting cross-references and image paths in markdown"
# Use python for robust path rewriting:
# - In markdown image refs ![alt](path/to/foo.bar/file.svg), replace dots
#   with dashes in every directory segment (keeping the final .svg extension)
# - In markdown link refs [text](path/to/foo.bar.baz/), replace dots
#   with dashes in every directory segment (handles .manual/, .runbook/,
#   .guardrails/, .model/, .architecture/, etc. uniformly)
export DOCS_DIR
python3 <<'PYEOF'
import os, re

DOCS_DIR = os.environ.get("DOCS_DIR")

# Match markdown image or link: ![alt](url) or [text](url)
link_re = re.compile(r'(!?\[[^\]]*\])\(([^)]+)\)')
# Also match HTML img src attributes: <img src="path">
html_img_re = re.compile(r'(<img[^>]*\ssrc=["\'])([^"\']+)(["\'])')

def rewrite_url(url: str) -> str:
    # Leave http(s), mailto, anchors, and absolute site paths starting with /
    # alone — only touch relative paths and /diagrams/ paths.
    if url.startswith(("http://", "https://", "mailto:", "#")):
        return url
    # Split URL at first # or ? to preserve the fragment/query
    frag = ""
    if "#" in url:
        url, _, anchor = url.partition("#")
        frag = "#" + anchor
    # Split into path parts
    parts = url.split("/")
    new_parts = []
    for i, p in enumerate(parts):
        # Skip empty parts and the final segment if it has a file extension
        if i == len(parts) - 1 and "." in p and p.rsplit(".", 1)[1] in (
            "svg", "png", "jpg", "jpeg", "gif", "webp", "md", "html", "pdf"
        ):
            new_parts.append(p)
        else:
            # Replace dots with dashes in directory segments
            new_parts.append(p.replace(".", "-"))
    return "/".join(new_parts) + frag

def transform_md(match):
    prefix = match.group(1)
    url = match.group(2)
    return f"{prefix}({rewrite_url(url)})"

def transform_html(match):
    prefix = match.group(1)
    url = match.group(2)
    suffix = match.group(3)
    return f"{prefix}{rewrite_url(url)}{suffix}"

for root, dirs, files in os.walk(DOCS_DIR):
    for f in files:
        if not f.endswith(".md"):
            continue
        path = os.path.join(root, f)
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        new_content = link_re.sub(transform_md, content)
        new_content = html_img_re.sub(transform_html, new_content)
        if new_content != content:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_content)
PYEOF

# ── Step 3: Homepage ─────────────────────────────────────────────────
# Skip if index.mdx already exists (the MDX version has Starlight components).
if [ -f "$DOCS_DIR/index.mdx" ]; then
    echo "--- Keeping existing index.mdx homepage"
else
    echo "--- Creating homepage from handover/README.md"
    cp "$HANDOVER_DIR/README.md" "$DOCS_DIR/index.md"
fi

# Use hsbc-deployment/README.md as its directory index
if [ -f "$HANDOVER_DIR/hsbc-deployment/README.md" ]; then
    cp "$HANDOVER_DIR/hsbc-deployment/README.md" "$DOCS_DIR/hsbc-deployment/index.md"
fi

# Create operations/handover.md from the handover README.
# This becomes the first page in "Operating the Platform" sidebar group.
if [ -f "$HANDOVER_DIR/README.md" ]; then
    echo "--- Creating operations/handover.md from handover/README.md"
    HANDOVER_README="$HANDOVER_DIR/README.md" HANDOVER_OUT="$DOCS_DIR/operations/handover.md" python3 <<'PYEOF'
import os, re

src = os.environ["HANDOVER_README"]
dst = os.environ["HANDOVER_OUT"]

with open(src) as f:
    body = f.read()

# Strip the first H1 line (Starlight renders title from frontmatter)
body = re.sub(r'^# .*\n', '', body, count=1)

# Drop everything up to and including the first "---" separator (the intro
# paragraphs about GitHub folder browsing are redundant inside Starlight).
body = re.sub(r'\A.*?^---\s*$\n', '', body, count=1, flags=re.DOTALL | re.MULTILINE)

# Collapse leading blank lines so the first heading sits flush under the title
body = body.lstrip('\n')

# Rewrite markdown links:
#   [text](operations/foo.md)        → [text](/operations/foo/)
#   [text](operations/foo.md#anchor) → [text](/operations/foo/#anchor)
#   [text](operations/foo.manual.md) → [text](/operations/foo-manual/)
#   [text](hsbc-deployment/README.md) → [text](/hsbc-deployment/) (README.md → section index)
#   [text](operations/)               → [text](/operations/platform-operations-manual/) (sections have no landing page; redirect to canonical first doc)
SECTION_INDEX = {
    "/operations/": "/operations/platform-operations-manual/",
    "/architecture/": "/architecture/detailed-architecture/",
    "/api/": "/api/api-common-spec/",
    "/component-designs/": "/component-designs/control-plane-design/",
    "/security/": "/security/authorization-spec/",
    "/governance/": "/governance/change-control-framework-governance/",
    "/standards/": "/standards/python-linting-standards/",
    "/sdk-manual/": "/sdk-manual/01-getting-started-manual/",
    "/developer-guide/": "/developer-guide/code-walkthrough/",
    "/reference/": "/reference/data-pipeline-reference/",
}

def rewrite(match):
    prefix = match.group(1)
    url = match.group(2)
    if url.startswith(("http://", "https://", "mailto:", "#")):
        return match.group(0)
    frag = ""
    if "#" in url:
        url, _, anchor = url.partition("#")
        frag = "#" + anchor
    if url.endswith(".md"):
        url = url[:-3]
    parts = [p.replace(".", "-") for p in url.split("/")]
    url = "/".join(parts)
    if not url.startswith("/"):
        url = "/" + url
    # README.md becomes the section's index.md, so strip trailing /README
    if url.endswith("/README"):
        url = url[:-len("README")]
    if not url.endswith("/"):
        url = url + "/"
    # Section-level links (no landing page) → redirect to canonical first doc
    if url in SECTION_INDEX:
        url = SECTION_INDEX[url]
    return f"{prefix}({url}{frag})"

link_re = re.compile(r'(\[[^\]]+\])\(([^)]+)\)')
body = link_re.sub(rewrite, body)

frontmatter = """---
title: Handover
sidebar:
  order: 0
---

"""
with open(dst, "w") as f:
    f.write(frontmatter + body)
PYEOF
fi

# ── Step 4: Copy SVG diagrams alongside markdown ────────────────────
# SVGs are nested under <section>/diagrams/<doc-name>/<file>.svg
# Copy them into src/content/docs/ preserving the relative structure
# so markdown image references (e.g., diagrams/foo/bar.svg) resolve.
echo "--- Copying SVG diagrams (renaming dots in subdirs)"
# SVGs go into BOTH src/content/docs/ (for markdown ![](diagrams/foo.svg) refs
# which Astro resolves via content collection) AND public/ (for HTML <img src>
# tags which the browser fetches as static assets at the URL given).
#
# For HTML tags we rewrite the src to an absolute path /<section>/diagrams/...
# so it resolves regardless of which page is viewing it (the browser otherwise
# resolves "diagrams/..." against the page URL which includes the slug segment).
cd "$HANDOVER_DIR"
find . -name '*.svg' -print0 | while IFS= read -r -d '' svg; do
    rel="${svg#./}"
    rel_dir="$(dirname "$rel")"
    rel_file="$(basename "$rel")"
    rel_dir_clean="${rel_dir//./-}"

    # Copy into src/content/docs/ (markdown refs, resolved by Astro)
    content_target="$DOCS_DIR/$rel_dir_clean/$rel_file"
    mkdir -p "$(dirname "$content_target")"
    cp "$svg" "$content_target"

    # Copy into public/ at the same relative path so absolute URLs
    # like /<section>/diagrams/<subdir>/<file>.svg serve from public/.
    public_target="$PROJECT_DIR/public/$rel_dir_clean/$rel_file"
    mkdir -p "$(dirname "$public_target")"
    cp "$svg" "$public_target"
done

# Rewrite HTML <img src="diagrams/..."> to absolute /<section>/diagrams/...
# so they don't resolve relative to the page URL (which includes the slug).
echo "--- Rewriting HTML img src to absolute paths"
export DOCS_DIR
python3 <<'PYEOF'
import os, re

DOCS_DIR = os.environ["DOCS_DIR"]
img_re = re.compile(r'(<img[^>]*\ssrc=["\'])(diagrams/[^"\']+)(["\'])')

for root, _, files in os.walk(DOCS_DIR):
    for f in files:
        if not f.endswith(".md"):
            continue
        path = os.path.join(root, f)
        # Section = relative directory from DOCS_DIR (e.g., "architecture")
        rel = os.path.relpath(os.path.dirname(path), DOCS_DIR)
        if rel == ".":
            continue
        section = rel.split(os.sep)[0]

        with open(path) as fh:
            content = fh.read()

        def repl(m):
            return f'{m.group(1)}/{section}/{m.group(2)}{m.group(3)}'

        new = img_re.sub(repl, content)
        if new != content:
            with open(path, "w") as fh:
                fh.write(new)
PYEOF

SVG_COUNT=$(find "$DOCS_DIR" -name '*.svg' | wc -l | tr -d ' ')
echo "    Copied $SVG_COUNT SVG diagrams"

# ── Step 5: Inject YAML frontmatter ──────────────────────────────────
# Starlight requires YAML frontmatter on every .md file. Most handover
# files have none. This step:
#   - Skips files that already have frontmatter (start with ---)
#   - Extracts the title from the first H1 heading (# ...)
#   - Escapes YAML-special characters in the title
#   - Adds sidebar.order based on the explicit sidebar config

echo "--- Injecting YAML frontmatter"

# Sidebar ordering map: slug -> order number.
# Slugs match the dash-renamed filenames (no dots).
declare -A SIDEBAR_ORDER

# Group 1: Getting Started
SIDEBAR_ORDER["hsbc-deployment/index"]=1
SIDEBAR_ORDER["hsbc-deployment/architecture"]=2
SIDEBAR_ORDER["hsbc-deployment/saml"]=3
SIDEBAR_ORDER["hsbc-deployment/jupyter"]=4
SIDEBAR_ORDER["hsbc-deployment/sdk-notebook-changes"]=5
SIDEBAR_ORDER["hsbc-deployment/query"]=6
SIDEBAR_ORDER["hsbc-deployment/debug"]=7

# Group 2: Operating the Platform
SIDEBAR_ORDER["operations/platform-operations-manual"]=1
SIDEBAR_ORDER["operations/service-catalogue-manual"]=2
SIDEBAR_ORDER["operations/configuration-reference"]=3
SIDEBAR_ORDER["operations/known-issues"]=4
SIDEBAR_ORDER["operations/gcs-bucket-management"]=5
SIDEBAR_ORDER["operations/job-sequence"]=6
SIDEBAR_ORDER["operations/capacity-planning-manual"]=7
SIDEBAR_ORDER["operations/monitoring-alerting-runbook"]=8
SIDEBAR_ORDER["operations/troubleshooting-runbook"]=9
SIDEBAR_ORDER["operations/incident-response-runbook"]=10
SIDEBAR_ORDER["operations/disaster-recovery-runbook"]=11
SIDEBAR_ORDER["operations/security-operations-runbook"]=12

# Group 3: System Architecture
SIDEBAR_ORDER["architecture/detailed-architecture"]=1
SIDEBAR_ORDER["architecture/domain-and-data"]=2
SIDEBAR_ORDER["architecture/data-model-spec"]=3
SIDEBAR_ORDER["architecture/domain-model-overview"]=4
SIDEBAR_ORDER["architecture/sdk-architecture"]=5
SIDEBAR_ORDER["architecture/authorization"]=6
SIDEBAR_ORDER["architecture/platform-operations"]=7
SIDEBAR_ORDER["architecture/requirements"]=8
SIDEBAR_ORDER["architecture/architectural-guardrails"]=9
SIDEBAR_ORDER["architecture/system-architecture-design"]=10
SIDEBAR_ORDER["api/api-common-spec"]=1
SIDEBAR_ORDER["api/api-instances-spec"]=2
SIDEBAR_ORDER["api/api-mappings-spec"]=3
SIDEBAR_ORDER["api/api-snapshots-spec"]=4
SIDEBAR_ORDER["api/api-wrapper-spec"]=5
SIDEBAR_ORDER["api/api-admin-ops-spec"]=6
SIDEBAR_ORDER["api/api-starburst-spec"]=7
SIDEBAR_ORDER["api/api-favorites-spec"]=8
SIDEBAR_ORDER["api/api-internal-spec"]=9
SIDEBAR_ORDER["component-designs/control-plane-design"]=1
SIDEBAR_ORDER["component-designs/control-plane-services-design"]=2
SIDEBAR_ORDER["component-designs/control-plane-background-jobs-design"]=3
SIDEBAR_ORDER["component-designs/control-plane-mapping-generator-design"]=4
SIDEBAR_ORDER["component-designs/export-worker-design"]=5
SIDEBAR_ORDER["component-designs/export-worker-clients-design"]=6
SIDEBAR_ORDER["component-designs/ryugraph-wrapper-design"]=7
SIDEBAR_ORDER["component-designs/ryugraph-wrapper-services-design"]=8
SIDEBAR_ORDER["component-designs/falkordb-wrapper-design"]=9
SIDEBAR_ORDER["component-designs/jupyter-sdk-design"]=10
SIDEBAR_ORDER["component-designs/jupyter-sdk-connection-design"]=11
SIDEBAR_ORDER["component-designs/jupyter-sdk-algorithms-design"]=12
SIDEBAR_ORDER["component-designs/jupyter-sdk-algorithms-native-design"]=13
SIDEBAR_ORDER["component-designs/jupyter-sdk-algorithms-networkx-design"]=14
SIDEBAR_ORDER["component-designs/jupyter-sdk-deployment-design"]=15
SIDEBAR_ORDER["component-designs/jupyter-sdk-models-spec"]=16
SIDEBAR_ORDER["component-designs/instance-lifecycle-management-design"]=17
SIDEBAR_ORDER["component-designs/e2e-tests-design"]=18

# Group 4: SDK & Tutorials
SIDEBAR_ORDER["sdk-manual/01-getting-started-manual"]=1
SIDEBAR_ORDER["sdk-manual/02-core-concepts-manual"]=2
SIDEBAR_ORDER["sdk-manual/03-api-reference-manual"]=3
SIDEBAR_ORDER["sdk-manual/04-graph-algorithms-manual"]=4
SIDEBAR_ORDER["sdk-manual/05-advanced-topics-manual"]=5
SIDEBAR_ORDER["sdk-manual/06-examples-manual"]=6
SIDEBAR_ORDER["sdk-manual/appendices/a-environment-variables-manual"]=1
SIDEBAR_ORDER["sdk-manual/appendices/b-error-codes-manual"]=2
SIDEBAR_ORDER["sdk-manual/appendices/c-cypher-reference-manual"]=3
SIDEBAR_ORDER["sdk-manual/appendices/d-algorithm-reference-manual"]=4

# Group 5: Security & Compliance
SIDEBAR_ORDER["security/authorization-spec"]=1
SIDEBAR_ORDER["security/transport-security-design"]=2
SIDEBAR_ORDER["security/container-security-audit"]=3
SIDEBAR_ORDER["security/security-improvements-summary"]=4
SIDEBAR_ORDER["governance/container-supply-chain-governance"]=5
SIDEBAR_ORDER["governance/change-control-framework-governance"]=6
SIDEBAR_ORDER["standards/python-linting-standards"]=1
SIDEBAR_ORDER["standards/python-logging-standards"]=2
SIDEBAR_ORDER["standards/python-commenting-standards"]=3
SIDEBAR_ORDER["standards/container-build-standards"]=4
SIDEBAR_ORDER["standards/notebook-design-system"]=5

# Group 6: Reference
SIDEBAR_ORDER["developer-guide/code-walkthrough"]=1
SIDEBAR_ORDER["reference/data-pipeline-reference"]=2
SIDEBAR_ORDER["reference/ryugraph-performance-reference"]=3
SIDEBAR_ORDER["reference/ryugraph-networkx-reference"]=4

# Homepage
SIDEBAR_ORDER["index"]=0

inject_frontmatter() {
    local filepath="$1"

    local has_frontmatter=false
    local has_title=false

    if head -1 "$filepath" | grep -q '^---'; then
        has_frontmatter=true
        # Detect title: within the opening frontmatter block (between the first pair of --- lines)
        if awk 'NR==1 && /^---$/{infm=1; next} infm && /^---$/{exit} infm && /^title:[[:space:]]/{found=1; exit} END{exit !found}' "$filepath"; then
            has_title=true
        fi
    fi

    # Nothing to do if frontmatter already has a title.
    if $has_frontmatter && $has_title; then
        return
    fi

    # Extract title from first H1 heading.
    local title=""
    title=$(grep -m 1 '^# ' "$filepath" | sed 's/^# //' || true)

    if [ -z "$title" ]; then
        # Fallback: derive from filename
        local basename
        basename=$(basename "$filepath" .md)
        title=$(echo "$basename" | sed -E 's/^[0-9]+-//; s/-(manual|design|spec|runbook|reference|governance)$//; s/-/ /g')
        title=$(echo "$title" | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')
    fi

    # YAML-escape the title
    local escaped_title
    escaped_title=$(printf '%s' "$title" | sed 's/"/\\"/g')

    # Case A: frontmatter exists but lacks title → splice a title line in after the opening ---
    if $has_frontmatter && ! $has_title; then
        local tmpfile
        tmpfile=$(mktemp)
        awk -v t="title: \"$escaped_title\"" 'NR==1 && /^---$/{print; print t; next} {print}' "$filepath" > "$tmpfile"
        mv "$tmpfile" "$filepath"
        return
    fi

    # Compute the slug (path relative to docs dir, without .md extension)
    local rel_path
    rel_path="${filepath#$DOCS_DIR/}"
    local slug
    slug="${rel_path%.md}"

    # Build frontmatter
    local frontmatter="---"
    frontmatter="$frontmatter
title: \"$escaped_title\""

    if [ -n "${SIDEBAR_ORDER[$slug]+set}" ]; then
        frontmatter="$frontmatter
sidebar:
  order: ${SIDEBAR_ORDER[$slug]}"
    fi

    frontmatter="$frontmatter
---"

    # Write frontmatter, then the file body with:
    # 1. First H1 heading removed (Starlight renders title from frontmatter)
    # 2. Metadata block (**Key:** Value lines before first ##) converted to a table
    local tmpfile
    tmpfile=$(mktemp)
    printf '%s\n' "$frontmatter" > "$tmpfile"
    awk '
        /^# / && !h1_found { h1_found=1; next }
        /^\*\*[A-Za-z ]+:\*\*/ && !first_h2 {
            if (!meta_started) {
                meta_started=1
                print "| | |"
                print "|---|---|"
            }
            gsub(/^\*\*/, "| **")
            gsub(/:\*\* /, "** | ")
            print $0 " |"
            next
        }
        /^---$/ && meta_started && !first_h2 { meta_started=0; print ""; next }
        /^## / { first_h2=1 }
        /^$/ && meta_started && !first_h2 { next }
        1
    ' "$filepath" >> "$tmpfile"
    mv "$tmpfile" "$filepath"
}

# Process all markdown files
INJECTED=0
SKIPPED=0
cd "$DOCS_DIR"
find . -name '*.md' -print0 | while IFS= read -r -d '' f; do
    filepath="$DOCS_DIR/${f#./}"
    # Let inject_frontmatter decide: it now handles three cases —
    # (a) no frontmatter → inject full block
    # (b) frontmatter present but no title → splice title line in
    # (c) frontmatter present with title → no-op
    inject_frontmatter "$filepath"
    INJECTED=$((INJECTED + 1))
done

echo "    Frontmatter injected"

# ── Step 6: Build (unless --copy-only) ────────────────────────────────
if [ "${1:-}" = "--copy-only" ]; then
    echo ""
    echo "==> Copy complete (--copy-only). Skipping npm build."
    echo "    Content:  $DOCS_DIR"
    echo "    Diagrams: $DIAGRAMS_DIR"
    exit 0
fi

echo "--- Building site"
cd "$PROJECT_DIR"
npm run build

echo ""
echo "==> Build complete."
echo "    Output: $PROJECT_DIR/dist/"
echo "    Serve:  npx serve dist/"
