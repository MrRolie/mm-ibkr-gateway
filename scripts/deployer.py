import os
import subprocess
import json
import typer
from dotenv import load_dotenv, set_key
from pathlib import Path

app = typer.Typer(help="Agent-focused IB Gateway Deployer")

ROOT_DIR = Path(__file__).parent.parent
ENV_FILE = ROOT_DIR / ".env"

@app.command()
def check():
    """Check if Docker is running and required ports are available."""
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
        typer.echo(json.dumps({"docker": "running"}))
    except subprocess.CalledProcessError:
        typer.echo(json.dumps({"docker": "not running", "error": "Docker daemon is not responsive."}))
        raise typer.Exit(1)

@app.command()
def setup():
    """Setup environment variables interactively if missing."""
    if not ENV_FILE.exists():
        ENV_FILE.touch()
    
    load_dotenv(ENV_FILE)
    userid = os.environ.get("TWS_USERID")
    password = os.environ.get("TWS_PASSWORD")
    mode = os.environ.get("TRADING_MODE", "paper")
    
    if not userid:
        userid = typer.prompt("Enter TWS_USERID")
        set_key(str(ENV_FILE), "TWS_USERID", userid)
    if not password:
        password = typer.prompt("Enter TWS_PASSWORD", hide_input=True)
        set_key(str(ENV_FILE), "TWS_PASSWORD", password)
    
    set_key(str(ENV_FILE), "TRADING_MODE", mode)
    typer.echo(json.dumps({"status": "setup complete", "env_file": str(ENV_FILE)}))

@app.command()
def up(detach: bool = True):
    """Start the IB Gateway container via docker compose."""
    cmd = ["docker", "compose", "up"]
    if detach:
        cmd.append("-d")
    
    try:
        subprocess.run(cmd, cwd=ROOT_DIR, check=True)
        typer.echo(json.dumps({"status": "started", "container": "ib-gateway"}))
    except subprocess.CalledProcessError as e:
        typer.echo(json.dumps({"status": "failed", "error": str(e)}))
        raise typer.Exit(1)

@app.command()
def down():
    """Stop the IB Gateway container."""
    try:
        subprocess.run(["docker", "compose", "down"], cwd=ROOT_DIR, check=True)
        typer.echo(json.dumps({"status": "stopped", "container": "ib-gateway"}))
    except subprocess.CalledProcessError as e:
        typer.echo(json.dumps({"status": "failed", "error": str(e)}))
        raise typer.Exit(1)

@app.command()
def status():
    """Get the status of the IB Gateway container."""
    try:
        res = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"], 
            cwd=ROOT_DIR, 
            capture_output=True, 
            text=True,
            check=True
        )
        output = res.stdout.strip()
        typer.echo(output if output else json.dumps([]))
    except subprocess.CalledProcessError as e:
        typer.echo(json.dumps({"error": f"Failed to get status: {e}"}))
        raise typer.Exit(1)

if __name__ == "__main__":
    app()