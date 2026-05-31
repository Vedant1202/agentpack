"""
One-off script: generate tests/fixtures/sample.pdf
Run: python tests/fixtures/create_sample_pdf.py
"""
import fitz
from pathlib import Path

OUT = Path(__file__).parent / "sample.pdf"


def make():
    doc = fitz.open()

    # ── Page 1: heading + paragraph ─────────────────────────────────────────
    p1 = doc.new_page(width=595, height=842)  # A4

    # Heading
    p1.insert_text((72, 80), "Introduction to AgentPack", fontsize=18, fontname="helv")

    # Paragraph
    body = (
        "AgentPack is a document-to-agent-context compiler. "
        "It ingests PDFs, Markdown, CSV, and plain text files, "
        "chunks them into semantically coherent blocks, "
        "and produces a manifest that LLM agents can query."
    )
    p1.insert_textbox(
        fitz.Rect(72, 120, 523, 300),
        body,
        fontsize=11,
        fontname="helv",
    )

    # Section heading
    p1.insert_text((72, 320), "Architecture Overview", fontsize=14, fontname="helv")
    p1.insert_textbox(
        fitz.Rect(72, 345, 523, 480),
        (
            "The pipeline consists of four stages: parsing, chunking, "
            "embedding, and indexing. Each stage is independently testable "
            "and produces well-typed intermediate artefacts."
        ),
        fontsize=11,
        fontname="helv",
    )

    # ── Page 2: table + closing paragraph ───────────────────────────────────
    p2 = doc.new_page(width=595, height=842)

    p2.insert_text((72, 60), "Supported Formats", fontsize=14, fontname="helv")

    # Draw a simple table manually
    rows = [
        ("Format", "Parser", "Semantic"),
        ("PDF", "PDFParser", "Yes (Docling)"),
        ("Markdown", "MarkdownParser", "Yes"),
        ("CSV", "CSVParser", "Table"),
        ("TXT", "TextParser", "No"),
    ]
    col_widths = [100, 150, 150]
    row_height = 22
    table_x, table_y = 72, 90

    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            x = table_x + sum(col_widths[:c_idx])
            y = table_y + r_idx * row_height
            rect = fitz.Rect(x, y, x + col_widths[c_idx], y + row_height)
            p2.draw_rect(rect, color=(0, 0, 0), width=0.5)
            p2.insert_text((x + 4, y + 15), cell, fontsize=10, fontname="helv")

    p2.insert_text((72, 230), "Conclusion", fontsize=14, fontname="helv")
    p2.insert_textbox(
        fitz.Rect(72, 255, 523, 380),
        (
            "AgentPack is designed to be extended. "
            "New parsers register themselves via a simple interface. "
            "The retrieval layer supports both lexical and semantic search."
        ),
        fontsize=11,
        fontname="helv",
    )

    doc.save(str(OUT))
    print(f"Written: {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    make()
