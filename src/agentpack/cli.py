import typer
from agentpack.pack import write_pack
from agentpack.validate import validate_pack
from agentpack.audit import audit_pack

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

if __name__ == "__main__":
    app()
