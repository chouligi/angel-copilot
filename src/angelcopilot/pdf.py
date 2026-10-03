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
            margin={"top": "17mm", "right": "14mm", "bottom": "18mm", "left": "14mm"},
            prefer_css_page_size=True,
            tagged=True,
            outline=True,
            display_header_footer=True,
            header_template="<div style='font-size:8px;color:#667085;width:100%;padding:0 14mm'>AngelCopilot · Investment Decisions</div>",
            footer_template="<div style='font-size:8px;color:#667085;width:100%;text-align:right;padding:0 14mm'>Page <span class='pageNumber'></span> of <span class='totalPages'></span></div>",
        )
        browser.close()
