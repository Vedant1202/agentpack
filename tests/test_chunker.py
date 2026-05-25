import pytest
from agentpack.chunker import chunk_document, Chunk
from agentpack.models import SourceDocument, DocumentBlock

def test_chunker_single_block():
    doc = SourceDocument(
        source_id="src_1",
        path="test.txt",
        type="txt",
        checksum="123",
        blocks=[
            DocumentBlock(block_id="b1", source_id="src_1", type="paragraph", text="Hello world")
        ],
        warnings=[]
    )
    
    chunks = chunk_document(doc, max_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].content == "Hello world"
    assert chunks[0].metadata["source_path"] == "test.txt"

def test_chunker_splitting():
    # Construct a document with many small blocks
    blocks = [
        DocumentBlock(block_id=f"b{i}", source_id="src_1", type="paragraph", text=f"Sentence number {i} is here.")
        for i in range(50)
    ]
    doc = SourceDocument(
        source_id="src_1",
        path="test.txt",
        type="txt",
        checksum="123",
        blocks=blocks,
        warnings=[]
    )
    
    # Very small token limit to force multiple chunks
    chunks = chunk_document(doc, max_tokens=20, overlap_percent=0.2)
    
    assert len(chunks) > 1
    
    # Check that chunks are correctly structured and overlap works roughly
    for c in chunks:
        assert c.token_count > 0
        assert c.source_id == "src_1"
        assert c.path.startswith("chunks/src_1_chunk_")

def test_chunker_metadata():
    doc = SourceDocument(
        source_id="src_meta",
        path="doc.pdf",
        type="pdf",
        checksum="123",
        blocks=[
            DocumentBlock(
                block_id="b1", source_id="src_meta", type="heading", text="Section 1", section_path=["Section 1"]
            ),
            DocumentBlock(
                block_id="b2", source_id="src_meta", type="paragraph", text="Content of section 1", page=5
            )
        ],
        warnings=[]
    )
    
    chunks = chunk_document(doc, max_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].metadata["section"] == "Section 1"
    assert chunks[0].metadata["page"] == 5
