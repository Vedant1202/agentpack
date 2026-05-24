import os
from pathlib import Path
from typing import List

SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf"}

def scan_directory(directory: str) -> List[Path]:
    """Recursively scans a directory and returns a list of supported files."""
    paths = []
    dir_path = Path(directory)
    for root, _, files in os.walk(dir_path):
        for file in files:
            p = Path(root) / file
            if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                paths.append(p)
    return paths
