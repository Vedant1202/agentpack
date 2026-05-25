import typer
from agentpack.pack import write_pack
from agentpack.validate import validate_pack
from agentpack.audit import audit_pack
from agentpack.retrieve import search_pack
from agentpack.eval.runner import run_eval

app = typer.Typer(help="AgentPack CLI", no_args_is_help=True)

@app.command()
def pack(input_dir: str, out: str = typer.Option(..., help="Output directory")):
    """Pack documents into an agent-friendly context pack."""
    typer.echo(f"Packing {input_dir} into {out}...")
    write_pack(input_dir, out)
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
    mode: str = typer.Option("hybrid", help="Search mode: hybrid, vector, or fts")
):
    """Retrieves top-k evidence chunks from a pack."""
    typer.echo(f"Searching for '{query}' in {pack_dir} using {mode} mode...")
    results = search_pack(pack_dir, query, top_k, mode=mode)
    
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
def gen_eval(benchmark_dir: str, gen_model: str = "gemini-3.5-flash", judge_model: str = "gemini-3.1-pro"):
    """Evaluate Generative QA using AgentPack"""
    from agentpack.eval.generation import run_generation_eval
    
    typer.echo(f"Running generative evaluation on {benchmark_dir}...")
    report = run_generation_eval(benchmark_dir, gen_model, judge_model)
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

if __name__ == "__main__":
    app()
