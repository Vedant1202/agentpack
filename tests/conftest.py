import pytest
import tempfile
import os
from pathlib import Path

@pytest.fixture
def mock_txt_file():
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write("This is a mock text file.\n\nIt has two paragraphs.")
    yield Path(path)
    os.remove(path)

@pytest.fixture
def mock_md_file():
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w") as f:
        f.write("# Main Title\n\nSome text.\n\n## Sub Title\n\nMore text.")
    yield Path(path)
    os.remove(path)

@pytest.fixture
def mock_csv_file():
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write("name,age,city\nAlice,30,New York\nBob,25,San Francisco")
    yield Path(path)
    os.remove(path)

@pytest.fixture
def mock_pdf_file():
    fd, path = tempfile.mkstemp(suffix=".pdf")
    # Write a dummy PDF signature just to pass basic file checks if needed
    # A real PyMuPDF test will mock the fitz module instead of parsing this.
    with os.fdopen(fd, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    yield Path(path)
    os.remove(path)
