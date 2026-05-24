from abc import ABC, abstractmethod
from pathlib import Path
from agentpack.models import SourceDocument

class Parser(ABC):
    @abstractmethod
    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        """Parses a file and returns a Canonical SourceDocument."""
        pass
