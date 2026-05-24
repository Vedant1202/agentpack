import typer
from agentpack.pack import write_pack

app = typer.Typer(help="AgentPack CLI")

@app.command()
def pack(input_dir: str, out: str = typer.Option(..., help="Output directory")):
    """Pack documents into an agent-friendly context pack."""
    typer.echo(f"Packing {input_dir} into {out}...")
    write_pack(input_dir, out)
    typer.echo("Done.")

if __name__ == "__main__":
    app()
