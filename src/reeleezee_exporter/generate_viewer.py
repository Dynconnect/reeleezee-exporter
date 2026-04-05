#!/usr/bin/env python3
"""
Generate HTML viewer from exported Reeleezee JSON data.

Takes an existing JSON export and generates a self-contained HTML viewer
that can be opened in a browser to navigate the exported data.

Usage:
    python -m reeleezee_exporter.generate_viewer --json exports/reeleezee_export.json
    python -m reeleezee_exporter.generate_viewer --json exports/data.json --template advanced
"""

import argparse
import re
import sys
from pathlib import Path


def generate_viewer(json_path: str, output_path: str, template: str = "advanced"):
    """Generate an HTML viewer from an existing JSON export.

    Args:
        json_path: Path to the JSON export file.
        output_path: Path for the output HTML file.
        template: Template to use ('basic' or 'advanced').
    """
    json_file = Path(json_path)
    if not json_file.exists():
        print(f"Error: JSON file not found: {json_path}")
        sys.exit(1)

    # Find the template
    package_dir = Path(__file__).parent.parent.parent
    template_name = "viewer_advanced.html" if template == "advanced" else "viewer.html"

    # Check multiple possible locations for the template
    template_paths = [
        package_dir / "viewers" / template_name,
        Path(__file__).parent / "viewers" / template_name,
    ]

    template_path = None
    for tp in template_paths:
        if tp.exists():
            template_path = tp
            break

    if not template_path:
        print(f"Error: Template not found: {template_name}")
        print(f"Searched in: {[str(p) for p in template_paths]}")
        sys.exit(1)

    # Read template
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Determine the export directory relative path
    export_dir = json_file.parent
    export_dir_name = export_dir.name + "/"

    # Update paths in template
    html = re.sub(
        r"return 'exports/reeleezee_export[^']*';",
        f"return '{export_dir_name}';",
        html,
    )
    html = re.sub(
        r"exports/reeleezee_export_\d{8}_\d{6}/",
        export_dir_name,
        html,
    )

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = Path(output_path).stat().st_size / 1024
    print(f"Viewer generated: {output_path} ({size_kb:.0f} KB)")
    print(f"Export directory: {export_dir_name}")


def main():
    """CLI entry point for viewer generation."""
    parser = argparse.ArgumentParser(
        description="Generate HTML viewer from Reeleezee JSON export",
    )
    parser.add_argument(
        "--json",
        required=True,
        help="Path to JSON export file or export directory",
    )
    parser.add_argument(
        "--template",
        choices=["basic", "advanced"],
        default="advanced",
        help="HTML template to use (default: advanced)",
    )
    parser.add_argument(
        "--output",
        help="Output HTML file path (default: same directory as JSON with .html extension)",
    )

    args = parser.parse_args()

    json_path = Path(args.json)
    if not json_path.exists():
        print(f"Error: not found: {json_path}")
        sys.exit(1)

    output_path = args.output or str(json_path.with_suffix(".html"))
    generate_viewer(str(json_path), output_path, args.template)


if __name__ == "__main__":
    main()
