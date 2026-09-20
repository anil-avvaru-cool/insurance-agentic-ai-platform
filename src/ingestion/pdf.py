"""PDF text parsing kept independent of metadata extraction."""

from pypdf import PdfReader


def parse_pdf(path):
    return '\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
