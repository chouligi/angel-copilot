"""PDF rendering helpers used by batch report generation."""

from __future__ import annotations

from pathlib import Path


def render_pdf_with_playwright(input_html: Path, output_pdf: Path) -> None:
    """Render an HTML report to PDF using Playwright.

    Args:
        input_html: Source HTML path.
        output_pdf: Destination PDF path.
    
    Returns:
        None.
    """

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        _render_with_python_playwright(input_html, output_pdf)
        return
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Could not render PDF with Python Playwright. "
            "Install Python package `playwright` and run `python -m playwright install chromium`. "
            f"Original error: {exc}"
        ) from exc


def _render_with_python_playwright(input_html: Path, output_pdf: Path) -> None:
    """Render PDF using the Python Playwright runtime.
    
    Args:
        input_html: Value for ``input_html``.
        output_pdf: Value for ``output_pdf``.
    
    Returns:
        None.
    """

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
