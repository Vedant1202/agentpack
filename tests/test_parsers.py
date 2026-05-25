import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agentpack.parsers.text_parser import TextParser
from agentpack.parsers.markdown_parser import MarkdownParser
from agentpack.parsers.csv_parser import CSVParser
from agentpack.parsers.pdf_parser import PDFParser

def test_text_parser(mock_txt_file):
    parser = TextParser()
    doc = parser.parse(mock_txt_file, "src_1")
    
    assert doc.type == "txt"
    assert len(doc.blocks) == 2
    assert doc.blocks[0].text == "This is a mock text file."
    assert doc.blocks[1].text == "It has two paragraphs."

def test_text_parser_remove_empty_lines(mock_txt_file):
    parser = TextParser()
    parser.remove_empty_lines = True
    doc = parser.parse(mock_txt_file, "src_1")
    
    # Because remove_empty_lines joins non-empty lines with \n, 
    # it compresses paragraphs into a single block since there are no \n\n anymore.
    assert len(doc.blocks) == 1
    assert "This is a mock text file.\nIt has two paragraphs." in doc.blocks[0].text

def test_markdown_parser(mock_md_file):
    parser = MarkdownParser()
    doc = parser.parse(mock_md_file, "src_1")
    
    # We expect blocks:
    # 1. Heading "Main Title"
    # 2. Paragraph "Some text."
    # 3. Heading "Sub Title"
    # 4. Paragraph "More text."
    assert len(doc.blocks) == 4
    assert doc.blocks[0].type == "heading"
    assert doc.blocks[0].text == "Main Title"
    assert doc.blocks[1].text == "Some text."
    
    assert doc.blocks[2].type == "heading"
    assert doc.blocks[2].text == "Sub Title"
    # Check section path injection
    assert doc.blocks[3].section_path == ["Main Title", "Sub Title"]

def test_markdown_parser_compression(mock_md_file):
    parser = MarkdownParser()
    parser.remove_empty_lines = True
    doc = parser.parse(mock_md_file, "src_1")
    
    # The removal of empty lines means paragraphs don't flush until the next heading
    # or EOF. It compresses text tightly.
    assert len(doc.blocks) == 4
    assert doc.blocks[1].text == "Some text."

def test_csv_parser(mock_csv_file):
    parser = CSVParser()
    doc = parser.parse(mock_csv_file, "src_csv")
    
    assert doc.type == "csv"
    assert len(doc.blocks) == 1
    assert doc.blocks[0].type == "table"
    # Tabulate outputs standard markdown table format by default in this implementation
    assert "Alice" in doc.blocks[0].text
    assert "San Francisco" in doc.blocks[0].text

@patch("agentpack.parsers.pdf_parser.fitz")
def test_pdf_parser(mock_fitz, mock_pdf_file):
    # Setup mock fitz Document
    mock_doc = MagicMock()
    mock_doc.page_count = 2
    
    mock_page_1 = MagicMock()
    mock_page_1.get_text.return_value = "Page 1 content."
    mock_page_2 = MagicMock()
    mock_page_2.get_text.return_value = "Page 2 content."
    
    # Mock doc[page_num] access
    def get_page(page_num):
        if page_num == 0: return mock_page_1
        if page_num == 1: return mock_page_2
        raise IndexError
    mock_doc.__getitem__.side_effect = get_page
    
    mock_fitz.open.return_value = mock_doc
    
    parser = PDFParser()
    doc = parser.parse(mock_pdf_file, "src_pdf")
    
    assert doc.type == "pdf"
    assert len(doc.blocks) == 2
    assert doc.blocks[0].text == "Page 1 content."
    assert doc.blocks[0].page == 1
    assert doc.blocks[1].text == "Page 2 content."
    assert doc.blocks[1].page == 2
