#!/usr/bin/env python3
"""
Update image dimensions in E2E notebooks.

Converts all image references to HTML <img> tags with max-height: 500px style.
"""

import json
import re
from pathlib import Path


def get_image_html(src: str, alt: str = "") -> str:
    """Generate HTML img tag with max-height style."""
    return f'<img src="{src}" style="max-height: 500px" alt="{alt}">'


def convert_markdown_image(match: re.Match) -> str:
    """Convert markdown image syntax to HTML."""
    alt = match.group(1)
    src = match.group(2)

    # Skip empty image placeholders
    if not src:
        return match.group(0)

    return get_image_html(src, alt)


def update_html_image(match: re.Match) -> str:
    """Update existing HTML img tag with max-height style."""
    full_tag = match.group(0)

    # Extract src
    src_match = re.search(r'src="([^"]+)"', full_tag)
    if not src_match:
        return full_tag
    src = src_match.group(1)

    # Extract alt (if present)
    alt_match = re.search(r'alt="([^"]*)"', full_tag)
    alt = alt_match.group(1) if alt_match else ""

    return get_image_html(src, alt)


def convert_python_image(source: str) -> str:
    """Convert Python Image() display to HTML in markdown cell."""
    # Pattern: display(Image(filename="...", width=N))
    pattern = r'display\s*\(\s*Image\s*\(\s*filename\s*=\s*["\']([^"\']+)["\'].*?\)\s*\)'

    def replace_image(match: re.Match) -> str:
        src = match.group(1)
        return get_image_html(src, Path(src).stem.replace("-", " ").title())

    return re.sub(pattern, replace_image, source, flags=re.DOTALL)


def process_cell(cell: dict) -> tuple[dict, bool]:
    """Process a single cell, return (new_cell, was_modified)."""
    if cell['cell_type'] == 'markdown':
        source = ''.join(cell['source'])
        new_source = source

        # Convert markdown images: ![alt](src)
        new_source = re.sub(r'!\[([^\]]*)\]\(([^)]*)\)', convert_markdown_image, new_source)

        # Update existing HTML img tags
        new_source = re.sub(r'<img[^>]+>', update_html_image, new_source)

        if new_source != source:
            lines = new_source.split('\n')
            cell['source'] = [line + '\n' if i < len(lines) - 1 else line
                             for i, line in enumerate(lines)]
            return cell, True

    elif cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        new_source = source

        # Update HTML img tags in code cells (e.g., in display(HTML(...)) or raw HTML)
        if '<img' in source:
            new_source = re.sub(r'<img[^>]+>', update_html_image, new_source)

        # Check for Python Image display
        if 'display(Image(' in new_source or 'display(Image (' in new_source:
            # Convert to markdown cell with HTML
            new_source = convert_python_image(new_source)

            # Remove IPython import if it becomes unused
            if 'from IPython.display import' in new_source:
                # Check if Image is still used
                if 'Image(' not in new_source:
                    new_source = re.sub(r'from IPython\.display import[^\n]*\n?', '', new_source)

        # Check if cell is now just comments and img tags - convert to markdown
        # Remove comments and blank lines to see what's left
        code_lines = [line for line in new_source.split('\n')
                     if line.strip() and not line.strip().startswith('#')]
        code_content = '\n'.join(code_lines).strip()

        # If only img tags remain, convert to markdown
        if code_content and all(line.strip().startswith('<img') for line in code_content.split('\n') if line.strip()):
            return {
                'cell_type': 'markdown',
                'metadata': {},
                'source': [line + '\n' if i < len(code_content.split('\n')) - 1 else line
                          for i, line in enumerate(code_content.split('\n'))]
            }, True

        # Return modified code cell if source changed
        if new_source != source:
            lines = new_source.split('\n')
            cell['source'] = [line + '\n' if i < len(lines) - 1 else line
                             for i, line in enumerate(lines)]
            return cell, True

    return cell, False


def process_notebook(notebook_path: Path) -> int:
    """Process a single notebook, return count of modified cells."""
    print(f"Processing: {notebook_path.name}")

    with open(notebook_path) as f:
        nb = json.load(f)

    modified_count = 0
    new_cells = []

    for cell in nb['cells']:
        new_cell, was_modified = process_cell(cell)
        new_cells.append(new_cell)
        if was_modified:
            modified_count += 1

    if modified_count > 0:
        nb['cells'] = new_cells
        with open(notebook_path, 'w') as f:
            json.dump(nb, f, indent=1)
        print(f"  Modified {modified_count} cells")
    else:
        print(f"  No changes")

    return modified_count


def main():
    """Process all notebooks."""
    notebooks_dir = Path(__file__).parent
    notebooks = sorted(notebooks_dir.glob('[0-9][0-9]_*.ipynb'))

    print(f"Found {len(notebooks)} notebooks\n")

    total_modified = 0
    for notebook_path in notebooks:
        modified = process_notebook(notebook_path)
        total_modified += modified

    print(f"\nTotal cells modified: {total_modified}")


if __name__ == '__main__':
    main()
