"""Rich terminal output helpers."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "flag": "bold magenta",
    }
)

console = Console(theme=THEME)

BANNER = r"""

             )   (
   (      ( /(   )\ )          )          )
   )\     )\()) (()/(    )  ( /(       ( /(   (    (   (
((((_)(  ((_)\   /(_))( /(  )\())  (   )\()) ))\  ))\  )(
 )\ _ )\  _((_) (_))  )(_))((_)\   )\ (_))/ /((_)/((_)(()\
 (_)_\(_)|_  /  / __|((_)_ | |(_) ((_)| |_ (_)) (_))(  ((_)
  / _ \   / /   \__ \/ _` || '_ \/ _ \|  _|/ -_)| || || '_|
 /_/ \_\ /___|  |___/\__,_||_.__/\___/ \__|\___| \_,_||_|


  Azure Cloud Dynamic Attack Lab Generator
"""

def print_banner() -> None:
    console.print(BANNER, style="bold #0099ff", highlight=False)


def print_success(message: str) -> None:
    console.print(f"{message}", style="success")


def print_error(message: str) -> None:
    console.print(f"{message}", style="error")


def print_warning(message: str) -> None:
    console.print(f"{message}", style="warning")


def print_info(message: str) -> None:
    console.print(f"{message}", style="info", highlight=False)


def print_flag(flag: str, step: int | None = None) -> None:
    prefix = f"Step {step}: " if step is not None else ""
    console.print(f"{prefix}{flag}", style="flag")


def print_mission_briefing(target: str, objective: str, connection_info: str) -> None:
    content = (
        f"[bold]Target:[/bold]      {target}\n"
        f"[bold]Objective:[/bold]   {objective}\n"
        f"[bold]Connect:[/bold]     {connection_info}"
    )
    console.print(Panel(content, title="YOUR MISSION BRIEFING", border_style="bold yellow"))


def print_chain_table(chain: list[dict]) -> None:
    table = Table(title="Attack Chain", show_lines=True)
    table.add_column("Step", style="bold", width=6)
    table.add_column("Module", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Category", style="yellow")
    for i, mod in enumerate(chain, 1):
        table.add_row(str(i), mod["id"], mod["name"], mod["category"])
    console.print(table)


def print_chain_summary(chain: list[dict]) -> None:
    """Brief chain overview showing only categories — safe for players to see."""
    categories = " → ".join(mod["category"] for mod in chain)
    console.print(
        f"Attack chain: [bold]{len(chain)}[/bold] steps  [{categories}]",
        style="info",
    )


def print_chain_verbose(chain: list[dict]) -> None:
    """Detailed chain info for debugging — not for player eyes."""
    console.print("[bold]Attack Chain Details:[/bold]")
    for i, mod in enumerate(chain, 1):
        console.print(
            f"  Step {i}: [cyan]{mod['id']}[/cyan] — {mod['name']} "
            f"[dim]({mod['category']})[/dim]"
        )
        if mod.get("description"):
            console.print(f"          {mod['description']}", style="dim")
    console.print()
