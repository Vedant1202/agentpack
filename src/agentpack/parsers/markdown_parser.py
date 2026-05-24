import hashlib
from pathlib import Path
from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning
from agentpack.parsers.base import Parser

class MarkdownParser(Parser):
    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        blocks = []
        warnings = []
        
        lines = content.split("\n")
        current_section_path = []
        current_paragraph_lines = []
        
        def push_paragraph():
            if current_paragraph_lines:
                text = "\n".join(current_paragraph_lines).strip()
                if text:
                    blocks.append(DocumentBlock(
                        block_id=f"{source_id}_b{len(blocks)}",
                        source_id=source_id,
                        type="paragraph",
                        text=text,
                        section_path=list(current_section_path)
                    ))
                current_paragraph_lines.clear()

        for line in lines:
            if line.startswith("#"):
                # Count hashes
                level = 0
                for char in line:
                    if char == "#":
                        level += 1
                    else:
                        break
                
                if level > 0 and len(line) > level and line[level] == " ":
                    push_paragraph()
                    title = line[level:].strip()
                    # Adjust section path
                    current_section_path = current_section_path[:level-1]
                    current_section_path.append(title)
                    
                    blocks.append(DocumentBlock(
                        block_id=f"{source_id}_b{len(blocks)}",
                        source_id=source_id,
                        type="heading",
                        text=title,
                        section_path=list(current_section_path)
                    ))
                    continue
            
            if not line.strip() and current_paragraph_lines:
                push_paragraph()
            elif line.strip():
                current_paragraph_lines.append(line)
                
        push_paragraph()
        
        if not blocks:
            warnings.append(ExtractionWarning(
                source_id=source_id,
                type="empty_file",
                message="Markdown file contained no meaningful content."
            ))

        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="markdown",
            checksum=checksum,
            blocks=blocks,
            warnings=warnings
        )
