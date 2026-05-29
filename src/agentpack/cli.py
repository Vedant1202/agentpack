import typer
from agentpack.pack import write_pack
from agentpack.validate import validate_pack
from agentpack.audit import audit_pack
from agentpack.retrieve import search_pack, build_fts_index, build_vector_index
from agentpack.eval.runner import run_eval

app = typer.Typer(help="AgentPack CLI", no_args_is_help=True)

@app.command()
def pack(
    input_dir: str, 
    out: str = typer.Option(..., help="Output directory"),
    include: str = typer.Option(None, help="Include only files matching these glob patterns (comma-separated)"),
    exclude: str = typer.Option(None, "-i", "--ignore", help="Additional patterns to exclude (comma-separated)"),
    no_gitignore: bool = typer.Option(False, help="Don't use .gitignore rules for filtering files"),
    no_default_patterns: bool = typer.Option(False, help="Don't apply built-in ignore patterns"),
    include_hidden: bool = typer.Option(False, help="Include hidden directories"),
    verbose: bool = typer.Option(False, help="Enable detailed debug logging"),
    quiet: bool = typer.Option(False, help="Suppress all console output except errors"),
    remove_empty_lines: bool = typer.Option(False, help="Remove blank lines from all text files"),
    fast: bool = typer.Option(False, "--fast", help="Fast mode: PyMuPDF parser + sqlite-vec backend"),
    fast_pdf: bool = typer.Option(False, "--fast-pdf", hidden=True, help="[Deprecated] Use --fast instead"),
):
    """Pack documents into an agent-friendly context pack."""
    if fast_pdf and not fast:
        typer.secho("Warning: --fast-pdf is deprecated; use --fast instead.", fg=typer.colors.YELLOW)
        fast = True

    if not quiet:
        typer.echo(f"Packing {input_dir} into {out}...")

    include_patterns = include.split(",") if include else None
    exclude_patterns = exclude.split(",") if exclude else None

    write_pack(
        input_dir=input_dir,
        output_dir=out,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        no_gitignore=no_gitignore,
        no_default_patterns=no_default_patterns,
        include_hidden=include_hidden,
        verbose=verbose,
        quiet=quiet,
        remove_empty_lines=remove_empty_lines,
        fast_pdf=fast,
    )
    
    if not quiet:
        typer.echo("Done.")

@app.command()
def validate(pack_dir: str):
    """Validates the structural integrity of a context pack."""
    typer.echo(f"Validating pack at {pack_dir}...")
    errors = validate_pack(pack_dir)
    if errors:
        typer.secho("Validation failed with errors:", fg=typer.colors.RED)
        for err in errors:
            typer.echo(f"- {err}")
        raise typer.Exit(code=1)
    else:
        typer.secho("Pack validation successful.", fg=typer.colors.GREEN)

@app.command()
def audit(pack_dir: str):
    """Generates an audit report for a context pack."""
    typer.echo(f"Auditing pack at {pack_dir}...")
    report = audit_pack(pack_dir)
    if report.startswith("Error:"):
        typer.secho(report, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    else:
        typer.echo(report)
        typer.secho("\nAudit report generated.", fg=typer.colors.GREEN)

@app.command()
def retrieve(
    pack_dir: str,
    query: str,
    top_k: int = typer.Option(5, help="Number of results to return"),
    mode: str = typer.Option("hybrid", help="Search mode: hybrid, vector, or fts"),
    source: str = typer.Option(None, help="Filter results to this source_id (substring match)"),
    section: str = typer.Option(None, help="Filter results to this section name (substring match)"),
    page: int = typer.Option(None, help="Filter results to this page number"),
):
    """Retrieves top-k evidence chunks from a pack."""
    typer.echo(f"Searching for '{query}' in {pack_dir} using {mode} mode...")
    results = search_pack(
        pack_dir, query, top_k, mode=mode,
        source_filter=source, section_filter=section, page_filter=page,
    )
    
    if not results:
        typer.secho("No results found.", fg=typer.colors.YELLOW)
        return
        
    for i, res in enumerate(results):
        source = res['citation'].get('source_path', res['source_id'])
        section = res['citation'].get('section', '')
        page = res['citation'].get('page', '')
        
        cite_str = source
        if page:
            cite_str += f", page {page}"
        if section:
            cite_str += f", {section}"
            
        typer.secho(f"\n{i+1}. {cite_str}", fg=typer.colors.CYAN, bold=True)
        typer.echo(f"   chunk: {res['path']}")
        typer.echo(f"   tokens: {res['token_count']}")
        typer.echo(f"   score: {res['score']:.2f}")

@app.command(name="index")
def index_cmd(
    pack_dir: str,
    quiet: bool = typer.Option(False, help="Suppress progress output"),
):
    """Build (or rebuild) FTS and vector indexes for a compiled pack."""
    from pathlib import Path as _Path

    base = _Path(pack_dir)
    indexes = base / "indexes"
    indexes.mkdir(exist_ok=True)

    if not quiet:
        typer.echo("Building FTS index…")
    build_fts_index(base, indexes / "lexical_index.db")

    if not quiet:
        typer.echo("Building vector index…")
    try:
        build_vector_index(base, indexes / "vector_index.npy", indexes / "vector_meta.json")
    except ImportError as e:
        typer.secho(f"Vector index skipped: {e}", fg=typer.colors.YELLOW)

    if not quiet:
        typer.secho("Index build complete.", fg=typer.colors.GREEN)


@app.command(name="eval")
def evaluate(benchmark_dir: str):
    """Runs a deterministic evaluation benchmark."""
    typer.echo(f"Running evaluation on {benchmark_dir}...")
    report = run_eval(benchmark_dir)
    if report.startswith("Error:"):
        typer.secho(report, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    else:
        typer.echo(report)
        typer.secho("\nEvaluation complete.", fg=typer.colors.GREEN)

@app.command(name="gen-eval")
def gen_eval(benchmark_dir: str, gen_model: str = "gemini-1.5-flash", judge_model: str = "gemini-1.5-pro", limit: int = typer.Option(None, help="Limit number of queries for a smoke test")):
    """Evaluate Generative QA using AgentPack"""
    from agentpack.eval.generation import run_generation_eval
    
    typer.echo(f"Running generative evaluation on {benchmark_dir}...")
    report = run_generation_eval(benchmark_dir, gen_model, judge_model, limit)
    if report.startswith("Error"):
        typer.secho(report, fg=typer.colors.RED)
    else:
        typer.echo(report)
        typer.secho("Generation evaluation complete.", fg=typer.colors.GREEN)

@app.command(name="prep-benchmark")
def prep_benchmark(dataset: str = typer.Option("financebench", help="Dataset to slice"), sample_size: int = typer.Option(10, help="Number of documents to sample")):
    """Downloads and slices a public dataset into a benchmark format."""
    from agentpack.eval.benchmarks import slice_financebench, slice_tatqa, slice_qasper
    
    out_dir = f"benchmarks/{dataset}_sample"
    typer.echo(f"Preparing {dataset} into {out_dir} with {sample_size} samples...")
    
    if dataset == "financebench":
        slice_financebench(out_dir, sample_size=sample_size)
    elif dataset == "tatqa":
        slice_tatqa(out_dir, sample_size=sample_size)
    elif dataset == "qasper":
        slice_qasper(out_dir, sample_size=sample_size)
    else:
        typer.secho(f"Unsupported dataset: {dataset}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    typer.secho("Preparation complete.", fg=typer.colors.GREEN)

@app.command()
def ui(pack_dir: str = typer.Argument(..., help="Path to compiled pack"), port: int = typer.Option(8000, help="Port to run the UI server on")):
    """Launch a local web UI to inspect your compiled context pack."""
    import os
    import sys
    from pathlib import Path
    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError:
        typer.secho("UI dependencies not found. Please run: pip install agentpack[ui]", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    typer.echo(f"Starting AgentPack Corpus Intelligence for {pack_dir} on port {port}...")
    
    # Set the pack_dir in the environment so server.py can read it
    os.environ["AGENTPACK_DIR"] = str(Path(pack_dir).resolve())
    
    # Run uvicorn
    uvicorn.run("agentpack.ui.server:app", host="127.0.0.1", port=port, reload=False)

if __name__ == "__main__":
    app()
