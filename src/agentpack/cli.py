import typer
from agentpack.pack import write_pack

app = typer.Typer(help="AgentPack CLI", no_args_is_help=True)

@app.command()
def pack(input_dir: str, out: str = typer.Option(..., help="Output directory")):
    """Pack documents into an agent-friendly context pack."""
    typer.echo(f"Packing {input_dir} into {out}...")
    write_pack(input_dir, out)
    typer.echo("Done.")

@app.command()
def inspect(pack_dir: str):
    """Inspect a generated context pack (Coming in Phase 2)."""
    typer.echo(f"Inspect not implemented yet for {pack_dir}")

if __name__ == "__main__":
    app()
