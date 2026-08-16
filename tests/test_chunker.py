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

def test_chunker_oversize_block():
    """A single block exceeding max_tokens must be split; metadata preserved on each sub-chunk."""
    import tiktoken
    encoder = tiktoken.get_encoding("cl100k_base")
    # Build ~5k-token text (well over default 800)
    long_text = " ".join(["word"] * 1200)
    assert len(encoder.encode(long_text)) > 800

    doc = SourceDocument(
        source_id="src_big",
        path="big.pdf",
        type="pdf",
        checksum="abc",
        blocks=[
            DocumentBlock(
                block_id="b0",
                source_id="src_big",
                type="paragraph",
                text=long_text,
                page=3,
                section_path=["Big Section"],
            )
        ],
        warnings=[],
    )

    chunks = chunk_document(doc, max_tokens=800)
    assert len(chunks) > 1, "oversized block must yield multiple chunks"
    for c in chunks:
        assert c.token_count <= 800, f"chunk exceeds max_tokens: {c.token_count}"
        assert c.metadata.get("page") == 3, "page metadata must carry on all sub-chunks"
        assert c.metadata.get("section") == "Big Section"


def test_chunker_boundary_chunk_cites_its_own_content_not_next_block():
    """F1: a chunk flushed at a block boundary must cite the page of the content actually
    inside it. block1 alone fits (700 <= 800); block1+block2 overflows, forcing a flush
    exactly at the boundary -- the flushed chunk is pure block1 (page 1) text."""
    block1_text = " ".join(["word"] * 700)
    block2_text = " ".join(["word"] * 700)

    doc = SourceDocument(
        source_id="src_bound",
        path="report.pdf",
        type="pdf",
        checksum="x",
        blocks=[
            DocumentBlock(block_id="b1", source_id="src_bound", type="paragraph",
                          text=block1_text, page=1, section_path=["Intro"]),
            DocumentBlock(block_id="b2", source_id="src_bound", type="paragraph",
                          text=block2_text, page=2, section_path=["Intro"]),
        ],
        warnings=[],
    )

    chunks = chunk_document(doc, max_tokens=800)
    assert len(chunks) >= 2, "block1 + block2 must overflow into at least 2 chunks"
    assert chunks[0].content.strip() == block1_text, "first chunk's content must be block1 only"
    assert chunks[0].metadata["page"] == 1, (
        f"first chunk is pure page-1 content but was stamped page={chunks[0].metadata.get('page')}"
    )


def test_chunker_boundary_chunk_cites_its_own_section_not_next_block():
    """Same bug, section_path axis: the flushed chunk must carry block1's section."""
    block1_text = " ".join(["word"] * 700)
    block2_text = " ".join(["word"] * 700)

    doc = SourceDocument(
        source_id="src_bound2",
        path="report.pdf",
        type="pdf",
        checksum="x",
        blocks=[
            DocumentBlock(block_id="b1", source_id="src_bound2", type="paragraph",
                          text=block1_text, section_path=["Introduction"]),
            DocumentBlock(block_id="b2", source_id="src_bound2", type="paragraph",
                          text=block2_text, section_path=["Usage"]),
        ],
        warnings=[],
    )

    chunks = chunk_document(doc, max_tokens=800)
    assert len(chunks) >= 2
    assert chunks[0].metadata["section"] == "Introduction", (
        f"first chunk is pure Introduction content but was stamped "
        f"section={chunks[0].metadata.get('section')!r}"
    )


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
