#!/usr/bin/env python3
"""
Convert E2E notebooks from Python-based HTML styling to pure Markdown.

This script converts notebooks that use display(notebook_header(...)), display(info_box(...)), etc.
into pure Markdown cells that render immediately without code execution.
"""

import json
import re
import html
from pathlib import Path
from typing import Optional


# HTML entity to Unicode mapping for icons
HTML_ENTITIES = {
    "&#127795;": "🌳",  # Tree
    "&#128203;": "📋",  # Clipboard
    "&#128269;": "🔍",  # Magnifying glass
    "&#128640;": "🚀",  # Rocket
    "&#128736;": "🔐",  # Lock
    "&#128202;": "📊",  # Chart
    "&#128221;": "📝",  # Memo
    "&#128214;": "📖",  # Book
    "&#128187;": "💻",  # Computer
    "&#127919;": "🎯",  # Target
    "&#128161;": "💡",  # Light bulb
    "&#9888;": "⚠️",   # Warning
    "&#10004;": "✔",   # Check mark
    "&#128200;": "📈",  # Chart increasing
    "&#128230;": "📦",  # Package
    "&#128295;": "🔧",  # Wrench
    "&#128300;": "🔬",  # Microscope
    "&#9881;": "⚙️",   # Gear
    "&#128196;": "📄",  # Document
    "&#128274;": "🔒",  # Locked
}


def decode_html_entities(text: str) -> str:
    """Convert HTML entities to Unicode characters."""
    if not text:
        return text
    # First try our mapping
    for entity, char in HTML_ENTITIES.items():
        text = text.replace(entity, char)
    # Then try standard HTML unescape
    return html.unescape(text)


def extract_string_arg(source: str, arg_name: str) -> Optional[str]:
    """Extract a string argument from a function call."""
    # Match arg_name="value" or arg_name='value'
    pattern = rf'{arg_name}\s*=\s*["\']([^"\']*)["\']'
    match = re.search(pattern, source, re.DOTALL)
    if match:
        return match.group(1)

    # Match arg_name="""value""" (triple quotes)
    pattern = rf'{arg_name}\s*=\s*"""(.*?)"""'
    match = re.search(pattern, source, re.DOTALL)
    if match:
        return match.group(1)

    return None


def extract_list_arg(source: str, arg_name: str) -> list:
    """Extract a list argument from a function call."""
    pattern = rf'{arg_name}\s*=\s*\[(.*?)\]'
    match = re.search(pattern, source, re.DOTALL)
    if match:
        items_str = match.group(1)
        # Extract quoted strings
        items = re.findall(r'["\']([^"\']+)["\']', items_str)
        return items
    return []


def extract_positional_list_arg(source: str, position: int) -> list:
    """Extract a positional list argument from a function call.

    For example: summary_checklist("Title", ["item1", "item2"])
    Position 1 would return ["item1", "item2"]
    """
    # Find the opening paren of the function call
    paren_start = source.find('(')
    if paren_start == -1:
        return []

    # Find matching closing paren
    paren_end = -1
    depth = 0
    in_string = None
    i = paren_start

    while i < len(source):
        char = source[i]
        if in_string:
            if in_string == '"""' and source[i:i+3] == '"""':
                in_string = None
                i += 3
                continue
            elif in_string == "'''" and source[i:i+3] == "'''":
                in_string = None
                i += 3
                continue
            elif in_string in ('"', "'") and char == in_string and (i == 0 or source[i-1] != '\\'):
                in_string = None
            i += 1
            continue

        if source[i:i+3] in ('"""', "'''"):
            in_string = source[i:i+3]
            i += 3
            continue
        if char in ('"', "'"):
            in_string = char
            i += 1
            continue

        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                paren_end = i
                break
        i += 1

    if paren_end == -1:
        return []

    # Get content between parens
    content = source[paren_start + 1:paren_end]

    # Split by top-level commas (not inside strings or nested parens)
    args = []
    current_arg = ""
    depth = 0
    in_string = None
    i = 0

    while i < len(content):
        char = content[i]
        if in_string:
            current_arg += char
            if in_string == '"""' and content[i:i+3] == '"""':
                in_string = None
                current_arg += content[i+1:i+3]
                i += 3
                continue
            elif in_string == "'''" and content[i:i+3] == "'''":
                in_string = None
                current_arg += content[i+1:i+3]
                i += 3
                continue
            elif in_string in ('"', "'") and char == in_string and (i == 0 or content[i-1] != '\\'):
                in_string = None
            i += 1
            continue

        if content[i:i+3] in ('"""', "'''"):
            in_string = content[i:i+3]
            current_arg += content[i:i+3]
            i += 3
            continue
        if char in ('"', "'"):
            in_string = char
            current_arg += char
            i += 1
            continue

        if char in '([{':
            depth += 1
            current_arg += char
        elif char in ')]}':
            depth -= 1
            current_arg += char
        elif char == ',' and depth == 0:
            args.append(current_arg.strip())
            current_arg = ""
        else:
            current_arg += char
        i += 1

    if current_arg.strip():
        args.append(current_arg.strip())

    if position >= len(args):
        return []

    arg = args[position]

    # Check if it's a list
    if not arg.startswith('['):
        return []

    # Extract items from the list
    items = re.findall(r'["\']([^"\']+)["\']', arg)
    return items


def strip_html_tags(text: str) -> str:
    """Remove HTML tags and clean up text for markdown."""
    if not text:
        return ""
    # Remove <p>, </p>, <ul>, </ul>, <li>, </li>, <br>, etc.
    text = re.sub(r'</?p[^>]*>', '', text)
    text = re.sub(r'</?ul[^>]*>', '', text)
    text = re.sub(r'<li[^>]*>', '- ', text)
    text = re.sub(r'</li>', '', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</?strong>', '**', text)
    text = re.sub(r'</?em>', '*', text)
    text = re.sub(r'</?code>', '`', text)
    text = re.sub(r'<[^>]+>', '', text)  # Remove any remaining tags
    # Clean up whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    return text.strip()


def convert_notebook_header(source: str) -> str:
    """Convert notebook_header() to markdown."""
    title = extract_string_arg(source, 'title') or "Untitled"
    subtitle = extract_string_arg(source, 'subtitle') or ""
    duration = extract_string_arg(source, 'duration') or "?"
    difficulty = extract_string_arg(source, 'difficulty') or "?"
    tags = extract_list_arg(source, 'tags')

    tag_str = ' '.join(f'`{t}`' for t in tags) if tags else ""

    return f"""# {title}

> **⏱️ {duration}** | **📊 {difficulty}**

{subtitle}

**Topics:** {tag_str}

---"""


def convert_section_header(source: str) -> str:
    """Convert section_header() to markdown."""
    # Extract positional args or named args
    # Pattern: section_header("title", "description", icon="...")
    match = re.search(r'section_header\s*\(\s*["\']([^"\']+)["\']', source)
    title = match.group(1) if match else "Section"

    # Get description (second positional arg)
    match = re.search(r'section_header\s*\([^,]+,\s*["\']([^"\']+)["\']', source)
    description = match.group(1) if match else ""

    # Get icon
    icon = extract_string_arg(source, 'icon') or "📚"
    icon = decode_html_entities(icon)

    result = f"## {icon} {title}"
    if description:
        result += f"\n\n{description}"
    return result


def convert_info_box(source: str) -> str:
    """Convert info_box() to markdown blockquote."""
    match = re.search(r'info_box\s*\(\s*["\']([^"\']+)["\']', source)
    title = match.group(1) if match else "Info"

    match = re.search(r'info_box\s*\([^,]+,\s*["\']([^"\']+)["\']', source)
    content = match.group(1) if match else ""
    content = strip_html_tags(content)

    return f"""> **ℹ️ {title}**
>
> {content}"""


def convert_warning_box(source: str) -> str:
    """Convert warning_box() to markdown blockquote."""
    match = re.search(r'warning_box\s*\(\s*["\']([^"\']+)["\']', source)
    title = match.group(1) if match else "Warning"

    match = re.search(r'warning_box\s*\([^,]+,\s*["\']([^"\']+)["\']', source)
    content = match.group(1) if match else ""
    content = strip_html_tags(content)

    return f"""> **⚠️ {title}**
>
> {content}"""


def convert_tip_box(source: str) -> str:
    """Convert tip_box() to markdown blockquote."""
    match = re.search(r'tip_box\s*\(\s*["\']([^"\']+)["\']', source)
    title = match.group(1) if match else "Tip"

    match = re.search(r'tip_box\s*\([^,]+,\s*["\']([^"\']+)["\']', source)
    content = match.group(1) if match else ""
    content = strip_html_tags(content)

    return f"""> **💡 {title}**
>
> {content}"""


def convert_success_box(source: str) -> str:
    """Convert success_box() to markdown blockquote."""
    match = re.search(r'success_box\s*\(\s*["\']([^"\']+)["\']', source)
    title = match.group(1) if match else "Success"

    match = re.search(r'success_box\s*\([^,]+,\s*["\']([^"\']+)["\']', source)
    content = match.group(1) if match else ""
    content = strip_html_tags(content)

    return f"""> **✅ {title}**
>
> {content}"""


def convert_error_box(source: str) -> str:
    """Convert error_box() to markdown blockquote."""
    match = re.search(r'error_box\s*\(\s*["\']([^"\']+)["\']', source)
    title = match.group(1) if match else "Error"

    match = re.search(r'error_box\s*\([^,]+,\s*["\']([^"\']+)["\']', source)
    content = match.group(1) if match else ""
    content = strip_html_tags(content)

    return f"""> **❌ {title}**
>
> {content}"""


def convert_concept_card(source: str) -> str:
    """Convert concept_card() to markdown."""
    title = extract_string_arg(source, 'title') or "Concept"
    description = extract_string_arg(source, 'description') or ""
    icon = extract_string_arg(source, 'icon') or "📚"
    icon = decode_html_entities(icon)

    description = strip_html_tags(description)

    return f"""### {icon} {title}

{description}"""


def convert_feature_card(source: str) -> str:
    """Convert feature_card() to markdown."""
    title = extract_string_arg(source, 'title') or "Feature"
    description = extract_string_arg(source, 'description') or ""
    icon = extract_string_arg(source, 'icon') or "✨"
    icon = decode_html_entities(icon)

    description = strip_html_tags(description)

    return f"""### {icon} {title}

{description}"""


def convert_image_with_caption(source: str) -> str:
    """Convert image_with_caption() to markdown."""
    src = extract_string_arg(source, 'src') or ""
    caption = extract_string_arg(source, 'caption') or ""
    alt = extract_string_arg(source, 'alt') or caption

    result = f"![{alt}]({src})"
    if caption:
        result += f"\n\n*{caption}*"
    return result


def convert_learn_more(source: str) -> str:
    """Convert learn_more() to HTML details block."""
    match = re.search(r'learn_more\s*\(\s*["\']([^"\']+)["\']', source)
    title = match.group(1) if match else "Learn More"

    # Content might be in second arg or as 'content' kwarg
    content = extract_string_arg(source, 'content') or ""
    if not content:
        match = re.search(r'learn_more\s*\([^,]+,\s*["\']([^"\']+)["\']', source)
        content = match.group(1) if match else ""

    content = strip_html_tags(content)

    return f"""<details>
<summary>📖 {title}</summary>

{content}

</details>"""


def convert_api_reference(source: str) -> str:
    """Convert api_reference() to markdown."""
    method = extract_string_arg(source, 'method') or "method()"
    description = extract_string_arg(source, 'description') or ""
    params = extract_string_arg(source, 'params') or ""
    returns = extract_string_arg(source, 'returns') or ""
    example = extract_string_arg(source, 'example') or ""

    description = strip_html_tags(description)
    params = strip_html_tags(params)
    returns = strip_html_tags(returns)

    result = f"""#### `{method}`

{description}

**Parameters:**
{params}

**Returns:** {returns}"""

    if example:
        result += f"""

```python
{example}
```"""

    return result


def convert_method_signature(source: str) -> str:
    """Convert method_signature() to markdown code block."""
    signature = extract_string_arg(source, 'signature') or ""
    description = extract_string_arg(source, 'description') or ""

    result = f"```python\n{signature}\n```"
    if description:
        result += f"\n\n{strip_html_tags(description)}"
    return result


def convert_key_takeaways(source: str) -> str:
    """Convert key_takeaways() to markdown list."""
    items = extract_list_arg(source, 'items')
    if not items:
        # Try to find items in the source
        items = re.findall(r'"([^"]+)"', source)
        items = [i for i in items if len(i) > 10]  # Filter short strings

    if not items:
        return "### ✅ Key Takeaways\n\n- (takeaways)"

    items_md = '\n'.join(f'- ✓ {strip_html_tags(item)}' for item in items)
    return f"""### ✅ Key Takeaways

{items_md}"""


def convert_next_steps(source: str) -> str:
    """Convert next_steps() to markdown links."""
    # This is complex - next_steps takes a list of dicts
    # For now, extract what we can
    notebooks = re.findall(r'"notebook":\s*"(\d+)"', source)
    titles = re.findall(r'"title":\s*"([^"]+)"', source)

    if not notebooks:
        return "### 🚀 Next Steps\n\n- Continue to next notebook"

    items = []
    for i, nb in enumerate(notebooks):
        title = titles[i] if i < len(titles) else f"Notebook {nb}"
        items.append(f"- **{nb}**: {title}")

    return f"""### 🚀 Next Steps

{chr(10).join(items)}"""


def convert_comparison_table(source: str) -> str:
    """Convert comparison_table() to markdown table."""
    headers = extract_list_arg(source, 'headers')
    # Rows are complex - list of lists
    # For now, return a placeholder
    if headers:
        header_row = '| ' + ' | '.join(headers) + ' |'
        sep_row = '| ' + ' | '.join(['---'] * len(headers)) + ' |'
        return f"{header_row}\n{sep_row}\n| (data) |"
    return "| Column 1 | Column 2 |\n|---|---|\n| data | data |"


def convert_styled_table(source: str) -> str:
    """Convert styled_table() - these typically wrap DataFrames, keep as code."""
    return None  # Return None to keep as code cell


# Mapping of function names to converters
def convert_divider(source: str) -> str:
    """Convert divider() to markdown horizontal rule."""
    return "---"


def convert_summary_checklist(source: str) -> str:
    """Convert summary_checklist() to markdown."""
    title = extract_positional_arg(source, 0) or "Summary"
    items = extract_list_arg(source, 'items') or extract_positional_list_arg(source, 1) or []

    if not items:
        return f"### ✅ {title}"

    item_lines = '\n'.join(f"- [x] {item}" for item in items)
    return f"""### ✅ {title}

{item_lines}"""


def convert_badge(source: str) -> str:
    """Convert badge() to inline markdown. Returns empty since badges are inline."""
    # Badges are used inline in other expressions, so we return empty
    # The calling code will handle this appropriately
    return ""


CONVERTERS = {
    'notebook_header': convert_notebook_header,
    'section_header': convert_section_header,
    'info_box': convert_info_box,
    'warning_box': convert_warning_box,
    'tip_box': convert_tip_box,
    'success_box': convert_success_box,
    'error_box': convert_error_box,
    'concept_card': convert_concept_card,
    'feature_card': convert_feature_card,
    'image_with_caption': convert_image_with_caption,
    'learn_more': convert_learn_more,
    'api_reference': convert_api_reference,
    'method_signature': convert_method_signature,
    'key_takeaways': convert_key_takeaways,
    'next_steps': convert_next_steps,
    'comparison_table': convert_comparison_table,
    'styled_table': convert_styled_table,
    'divider': convert_divider,
    'summary_checklist': convert_summary_checklist,
    'badge': convert_badge,
}


def find_matching_paren(source: str, start: int) -> int:
    """Find the index of the closing parenthesis matching the one at start."""
    depth = 0
    i = start
    in_string = None

    while i < len(source):
        char = source[i]

        # Handle being inside a string
        if in_string:
            # Check for end of triple quotes
            if in_string == '"""' and source[i:i+3] == '"""':
                in_string = None
                i += 3
                continue
            elif in_string == "'''" and source[i:i+3] == "'''":
                in_string = None
                i += 3
                continue
            elif in_string in ('"', "'") and char == in_string:
                # Check for escaped quote
                if i > 0 and source[i-1] == '\\':
                    i += 1
                    continue
                in_string = None
            i += 1
            continue

        # Check for start of strings
        if source[i:i+3] in ('"""', "'''"):
            in_string = source[i:i+3]
            i += 3
            continue
        if char in ('"', "'"):
            in_string = char
            i += 1
            continue

        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return -1


def extract_display_call(source: str, start: int) -> tuple:
    """Extract a complete display() call starting at given position.
    Returns (call_source, end_index) or (None, -1) if not found."""
    # Find the opening paren of display(
    paren_start = source.find('(', start)
    if paren_start == -1:
        return None, -1

    # Find matching closing paren
    paren_end = find_matching_paren(source, paren_start)
    if paren_end == -1:
        return None, -1

    return source[start:paren_end + 1], paren_end + 1


def find_display_calls(source: str) -> list:
    """Find all display() calls in source and return (function_name, full_call) tuples."""
    calls = []

    # Pattern 1: display(fn_name(...)) - function with arguments
    pattern = r'display\s*\(\s*(\w+)\s*\('
    for match in re.finditer(pattern, source):
        fn_name = match.group(1)
        call_start = match.start()
        full_call, _ = extract_display_call(source, call_start)
        if full_call:
            calls.append((fn_name, full_call))

    # Pattern 2: display(fn_name()) - function with no arguments (like divider())
    pattern2 = r'display\s*\(\s*(\w+)\s*\(\s*\)\s*\)'
    for match in re.finditer(pattern2, source):
        fn_name = match.group(1)
        full_call = match.group(0)
        # Only add if not already captured
        if not any(call == full_call for _, call in calls):
            calls.append((fn_name, full_call))

    return calls


def find_inline_style_calls(source: str) -> list:
    """Find inline style function calls not wrapped in display().

    Examples: status = badge("Set", "green")
    """
    calls = []

    for fn_name in CONVERTERS.keys():
        # Pattern: fn_name( at word boundary
        pattern = rf'(?<!\w){fn_name}\s*\('
        for match in re.finditer(pattern, source):
            call_start = match.start()

            # Check if this is inside a display() call - if so, skip it
            # Look backwards for display(
            before = source[:call_start]
            if re.search(r'display\s*\(\s*$', before):
                continue

            # Find the opening paren
            paren_start = source.find('(', call_start)
            if paren_start == -1:
                continue
            paren_end = find_matching_paren(source, paren_start)
            if paren_end == -1:
                continue
            full_call = source[call_start:paren_end + 1]
            calls.append((fn_name, full_call))

    return calls


def convert_cell_source(source: str) -> Optional[str]:
    """Convert a code cell source to markdown if it contains style functions."""
    display_calls = find_display_calls(source)

    if not display_calls:
        return None

    # Check if any are style functions
    style_calls = [(fn, call) for fn, call in display_calls if fn in CONVERTERS]
    if not style_calls:
        return None

    # Convert each display call
    markdown_parts = []

    for fn_name, call_source in style_calls:
        converter = CONVERTERS.get(fn_name)
        if converter:
            result = converter(call_source)
            if result is not None:
                markdown_parts.append(result)

    if not markdown_parts:
        return None

    return '\n\n'.join(markdown_parts)


def is_import_cell(source: str) -> bool:
    """Check if this is the notebook_styles import cell."""
    return 'from notebook_styles import' in source or 'import notebook_styles' in source


def is_pure_style_cell(source: str) -> bool:
    """Check if cell contains ONLY style display() calls (no real code)."""
    # Find and remove all display() calls
    cleaned = source
    display_calls = find_display_calls(source)

    # Remove each display call from the source
    for _, call in display_calls:
        cleaned = cleaned.replace(call, '')

    # Remove comments and whitespace
    cleaned = re.sub(r'#.*', '', cleaned)
    cleaned = cleaned.strip()

    # If nothing left, it's a pure style cell
    return len(cleaned) == 0


def is_pure_import_cell(source: str) -> bool:
    """Check if cell contains ONLY notebook_styles imports (no display calls)."""
    # Must have notebook_styles import
    if 'notebook_styles' not in source:
        return False

    # Check if there are any display calls
    display_calls = find_display_calls(source)
    if display_calls:
        return False

    # Check if there's any other substantial code beyond imports
    # Remove import lines
    cleaned = re.sub(r'^\s*(from|import)\s+.*$', '', source, flags=re.MULTILINE)
    # Remove init_styles() call
    cleaned = re.sub(r'init_styles\s*\(\s*\)', '', cleaned)
    # Remove comments and whitespace
    cleaned = re.sub(r'#.*', '', cleaned)
    cleaned = cleaned.strip()

    return len(cleaned) == 0


def has_style_display_calls(source: str) -> bool:
    """Check if source has display calls for style functions."""
    display_calls = find_display_calls(source)
    return any(fn in CONVERTERS for fn, _ in display_calls)


def remove_style_imports(source: str) -> str:
    """Remove notebook_styles import lines from source."""
    lines = source.split('\n')
    new_lines = []
    for line in lines:
        # Skip notebook_styles imports
        if 'from notebook_styles import' in line:
            continue
        if 'import notebook_styles' in line:
            continue
        # Skip init_styles() calls
        if re.match(r'^\s*init_styles\s*\(\s*\)\s*$', line):
            continue
        new_lines.append(line)
    return '\n'.join(new_lines)


def remove_style_display_calls(source: str) -> str:
    """Remove style display() calls from source while keeping real code.

    This handles mixed cells that have both real Python code and styling calls.
    The styling calls are removed entirely, leaving just the functional code.
    """
    result = source

    # Find and remove display(fn_name(...)) calls
    display_calls = find_display_calls(source)
    style_calls = [(fn, call) for fn, call in display_calls if fn in CONVERTERS]
    for _, call in style_calls:
        result = result.replace(call, '')

    # Find and remove inline style function calls (not wrapped in display)
    inline_calls = find_inline_style_calls(result)
    for fn_name, call in inline_calls:
        if fn_name in CONVERTERS:
            # For inline calls like: status = badge("Set", "green")
            # Remove the entire line that contains the call
            lines = result.split('\n')
            new_lines = []
            for line in lines:
                if call in line:
                    # Skip the entire line - don't try to preserve partial code
                    continue
                new_lines.append(line)
            result = '\n'.join(new_lines)

    # Remove lines that reference styling-related variables that no longer exist
    # Common patterns: rows.append with status, styled_table calls, etc.
    lines = result.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip empty lines but keep them for structure
        if not stripped:
            new_lines.append(line)
            continue
        # Skip lines that only manipulate 'rows' list (display-only code)
        if re.match(r'^\s*rows\s*=\s*\[\s*\]', stripped):
            continue
        if re.match(r'^\s*rows\.append\s*\(', stripped):
            continue
        # Skip standalone variable assignments that are now orphaned
        if re.match(r'^\s*(status|display_value)\s*=', stripped):
            continue
        new_lines.append(line)
    result = '\n'.join(new_lines)

    # Clean up empty lines (collapse multiple blank lines)
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)

    # Clean up leading/trailing blank lines
    result = result.strip()

    return result


def has_syntax_error(source: str) -> bool:
    """Check if the source code has Python syntax errors."""
    try:
        compile(source, '<string>', 'exec')
        return False
    except SyntaxError:
        return True


def is_display_only_cell(source: str) -> bool:
    """Check if a cell's only purpose was styling/display and should be deleted.

    Returns True if the cell:
    - Has syntax errors (broken after cleanup)
    - Has no print/assert statements
    - Has no API calls (client.*)
    - Only manipulates data for display purposes
    """
    # If the cell has syntax errors after cleanup, delete it
    if has_syntax_error(source):
        return True

    # Keep cells with print statements
    if 'print(' in source:
        return False

    # Keep cells with assertions
    if 'assert ' in source:
        return False

    # Keep cells with API calls
    if re.search(r'client\.\w+', source):
        return False

    # Keep cells with class/function definitions
    if re.search(r'^\s*(def |class )', source, re.MULTILINE):
        return False

    # Keep cells with IPython display of non-style content (like Images)
    if 'Image(' in source:
        return False

    # If the cell only has variable assignments, loops building rows, etc. - delete it
    # Check if any lines do something meaningful
    meaningful_patterns = [
        r'raise\s+',           # Raises exceptions
        r'return\s+',          # Returns values
        r'yield\s+',           # Generators
        r'await\s+',           # Async code
        r'\.create\(',         # API create calls
        r'\.get\(',            # API get calls
        r'\.list\(',           # API list calls
        r'\.delete\(',         # API delete calls
        r'\.query\(',          # Query calls
        r'\.run\(',            # Run calls
    ]

    for pattern in meaningful_patterns:
        if re.search(pattern, source):
            return False

    return True


def convert_notebook(notebook_path: Path) -> dict:
    """Convert a single notebook from Python HTML to Markdown."""
    print(f"Converting: {notebook_path.name}")

    with open(notebook_path) as f:
        nb = json.load(f)

    new_cells = []
    stats = {'converted': 0, 'removed': 0, 'kept': 0}

    for cell in nb['cells']:
        if cell['cell_type'] != 'code':
            new_cells.append(cell)
            continue

        source = ''.join(cell['source'])

        # Skip pure import cells (only imports, no display calls)
        if is_pure_import_cell(source):
            stats['removed'] += 1
            continue

        # Check if it has style display calls
        if has_style_display_calls(source):
            # Remove any notebook_styles imports from the source
            cleaned_source = remove_style_imports(source)

            # Check if it's a pure style cell (only display calls after import removal)
            if is_pure_style_cell(cleaned_source):
                markdown = convert_cell_source(cleaned_source)
                if markdown:
                    # Split markdown into lines for notebook format
                    lines = markdown.split('\n')
                    # Add newlines back except for last line
                    source_lines = [line + '\n' for line in lines[:-1]]
                    if lines:
                        source_lines.append(lines[-1])

                    new_cells.append({
                        'cell_type': 'markdown',
                        'metadata': {},
                        'source': source_lines
                    })
                    stats['converted'] += 1
                else:
                    # Couldn't convert, keep as is but without imports
                    cell['source'] = cleaned_source.split('\n')
                    new_cells.append(cell)
                    stats['kept'] += 1
            else:
                # Has real code mixed with style calls - keep code, remove style calls
                cleaned_source = remove_style_display_calls(cleaned_source)
                if cleaned_source.strip():
                    # Check if the remaining code is useful or just display-related leftovers
                    if is_display_only_cell(cleaned_source):
                        # Cell was only for display, delete it
                        stats['removed'] += 1
                    else:
                        lines = cleaned_source.split('\n')
                        cell['source'] = [line + '\n' if i < len(lines) - 1 else line
                                          for i, line in enumerate(lines)]
                        new_cells.append(cell)
                        stats['kept'] += 1
                else:
                    # Nothing left after removing style calls, skip the cell
                    stats['removed'] += 1
        else:
            # No style calls, keep as is
            new_cells.append(cell)
            stats['kept'] += 1

    nb['cells'] = new_cells

    print(f"  Converted: {stats['converted']}, Removed: {stats['removed']}, Kept: {stats['kept']}")
    return nb


def main():
    """Convert all notebooks in the current directory."""
    notebooks_dir = Path(__file__).parent
    notebooks = sorted(notebooks_dir.glob('[0-9][0-9]_*.ipynb'))

    print(f"Found {len(notebooks)} notebooks to convert\n")

    for notebook_path in notebooks:
        nb = convert_notebook(notebook_path)

        # Write back
        with open(notebook_path, 'w') as f:
            json.dump(nb, f, indent=1)

        print()

    print("Done!")


if __name__ == '__main__':
    main()
