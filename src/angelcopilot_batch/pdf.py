from __future__ import annotations

import subprocess
from pathlib import Path


def render_pdf_with_playwright(input_html: Path, output_pdf: Path) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    python_error: Exception | None = None
    try:
        _render_with_python_playwright(input_html, output_pdf)
        return
    except Exception as exc:  # noqa: BLE001
        python_error = exc

    try:
        _render_with_node_playwright(input_html, output_pdf)
        return
    except Exception as node_error:  # noqa: BLE001
        raise RuntimeError(
            "Could not render PDF. Install Playwright for Python or Node with Chromium browser. "
            f"Python error: {python_error}; Node error: {node_error}"
        ) from node_error


def _render_with_python_playwright(input_html: Path, output_pdf: Path) -> None:
    from playwright.sync_api import sync_playwright  # type: ignore

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(input_html.resolve().as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(output_pdf),
            format="A4",
            print_background=True,
            margin={"top": "16mm", "right": "12mm", "bottom": "16mm", "left": "12mm"},
        )
        browser.close()


def _render_with_node_playwright(input_html: Path, output_pdf: Path) -> None:
    script = r"""
const { chromium } = require('playwright');
(async () => {
  const input = process.argv[1];
  const output = process.argv[2];
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const url = 'file://' + input;
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.pdf({
    path: output,
    format: 'A4',
    printBackground: true,
    margin: { top: '16mm', right: '12mm', bottom: '16mm', left: '12mm' },
  });
  await browser.close();
})();
"""

    subprocess.run(
        ["node", "-e", script, str(input_html.resolve()), str(output_pdf.resolve())],
        check=True,
        capture_output=True,
        text=True,
    )
