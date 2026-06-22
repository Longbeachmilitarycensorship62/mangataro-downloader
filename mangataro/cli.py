"""MangaTaro Downloader — Typer CLI (direct commands)."""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.box import ROUNDED

from mangataro.config import Config
from mangataro.engine import (
    get_manga_info, get_chapter_list, get_chapters_rev,
    get_chapter_images, get_chapter_id_from_url,
    extract_slug, download_image,
)
from mangataro.search import search_manga
from mangataro.export import export_chapter, EXPORT_FORMATS, EXPORT_DESCRIPTIONS
from mangataro.history import History

app = typer.Typer(
    name="mangataro",
    help="📚 MangaTaro Downloader — Download and manage manga from MangaTaro.org",
    no_args_is_help=True,
)
console = Console()

# ── Callbacks ───────────────────────────────────────────────────────────

def _get_config() -> Config:
    return Config.load()


# ── Info Command ────────────────────────────────────────────────────────

@app.command()
def info(
    url_or_slug: str = typer.Argument(..., help="Manga URL or slug"),
):
    """📖 Get detailed info about a manga."""
    slug = extract_slug(url_or_slug)
    with console.status(f"Fetching info for [bold]{slug}[/bold]..."):
        manga = get_manga_info(slug)

    if not manga.title:
        console.print("[red]✗ Manga not found.[/red]")
        raise typer.Exit(1)

    # Header panel
    title_str = manga.title
    if manga.original_title:
        title_str += f" [dim]({manga.original_title})[/dim]"
    console.print(Panel(
        f"[bold magenta]{title_str}[/bold magenta]\n\n"
        f"[cyan]Status:[/cyan] {manga.status}  "
        f"[cyan]Type:[/cyan] {manga.type}  "
        f"[cyan]Views:[/cyan] {manga.views}\n"
        f"[cyan]Chapters:[/cyan] {manga.total_chapters}  "
        f"[cyan]Authors:[/cyan] {', '.join(manga.authors) if manga.authors else 'N/A'}\n\n"
        f"[yellow]MAL:[/yellow] Score {manga.mal_score}  |  "
        f"Rank #{manga.mal_rank}  |  "
        f"Pop #{manga.mal_popularity}  |  "
        f"Members {manga.mal_members}\n\n"
        f"[dim]{manga.description[:500]}[/dim]",
        title="📚 Manga Info",
        border_style="magenta",
        box=ROUNDED,
    ))

    # Genres row
    if manga.genres:
        genres_str = " • ".join(f"[cyan]{g}[/cyan]" for g in manga.genres)
        console.print(f"[bold]Genres:[/bold] {genres_str}")

    # Tags
    if manga.tags:
        tags_str = " ".join(f"[dim]#{t}[/dim]" for t in manga.tags)
        console.print(f"[bold]Tags:[/bold] {tags_str}")

    # Chapter list
    try:
        chapters = get_chapter_list(manga.id, manga.slug)
        console.print(f"\n[bold]Chapters:[/bold] {len(chapters)} total")
        rev = get_chapters_rev(chapters)
        if rev:
            table = Table("Idx", "Chapter", "Title", "Date", "Pages?", box=ROUNDED)
            for i, ch in enumerate(rev[:20], 1):
                table.add_row(str(i), ch.chapter, ch.title or "—", ch.date[:10] if ch.date else "—", "✓")
            if len(rev) > 20:
                table.add_row("...", f"... ({len(rev) - 20} more)", "", "", "")
            console.print(table)
    except Exception as e:
        console.print(f"[yellow]⚠ Could not fetch chapters: {e}[/yellow]")


# ── Search Command ──────────────────────────────────────────────────────

@app.command()
def search(
    query: str = typer.Argument(..., help="Manga name to search"),
    limit: int = typer.Option(24, "--limit", "-l", help="Max results"),
):
    """🔍 Search for manga by name."""
    with console.status(f"Searching for [bold]{query}[/bold]..."):
        result = search_manga(query, limit)

    if not result.results:
        console.print(f"[yellow]No results for \"{query}\"[/yellow]")
        raise typer.Exit(0)

    table = Table(
        "Idx", "Title", "Type", "Status", "Chapters", "Rating",
        box=ROUNDED, title=f"Results for \"{result.query}\" ({result.count})",
    )
    for i, m in enumerate(result.results, 1):
        status_icon = "🟢" if m.status == "Ongoing" else "🔴" if m.status == "Completed" else "🟡"
        table.add_row(
            str(i),
            f"[cyan]{m.title}[/cyan]",
            m.type or "—",
            f"{status_icon} {m.status}" if m.status else "—",
            str(m.chapter_count) if m.chapter_count else "—",
            m.rating or "—",
        )
    console.print(table)
    console.print(f"\n[dim]Tip: use [bold]mangataro info [slug][/bold] for details[/dim]")


# ── Download Command ────────────────────────────────────────────────────

@app.command()
def download(
    url_or_slug: str = typer.Argument(..., help="Manga URL or slug"),
    chapters: str = typer.Option("1", "--chapters", "-c", help="Chapter(s) to download (e.g. 1, 1-5, all)"),
    format: str = typer.Option("images", "--format", "-f", help=f"Export format: {', '.join(EXPORT_FORMATS)}"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    delete_images: bool = typer.Option(False, "--delete", "-d", help="Delete source images after export"),
):
    """⬇️ Download manga chapters."""
    config = _get_config()
    fmt = format.lower()
    if fmt not in EXPORT_FORMATS:
        console.print(f"[red]Invalid format '{fmt}'. Choose: {', '.join(EXPORT_FORMATS)}[/red]")
        raise typer.Exit(1)

    output_dir = output or Path(config.output_dir)

    slug = extract_slug(url_or_slug)
    with console.status(f"Fetching info..."):
        manga = get_manga_info(slug)

    if not manga.title:
        console.print("[red]✗ Manga not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Manga:[/bold] {manga.title}")
    with console.status("Fetching chapter list..."):
        chapters_data = get_chapter_list(manga.id, slug)
    rev = get_chapters_rev(chapters_data)

    # Parse chapter selection
    sel_chapters = []
    if chapters.lower() == "all":
        sel_chapters = rev
    else:
        nums = set()
        for part in chapters.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    s, e = part.split("-", 1)
                    nums.update(range(int(s), int(e) + 1))
                except ValueError:
                    pass
            elif part.isdigit():
                nums.add(int(part))
        sel_chapters = [c for c in rev if c.chapter_num in nums]

    if not sel_chapters:
        console.print("[yellow]No matching chapters found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"Downloading [bold]{len(sel_chapters)}[/bold] chapter(s) to [cyan]{output_dir / '...'}[/cyan]")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn
    from mangataro.engine import download_images_concurrent

    total_imgs = 0
    max_ch_workers = config.download.max_concurrent_chapters
    max_img_workers = config.download.max_concurrent_images

    def _dl_one_chapter(ch) -> tuple[str, int]:
        ch_id = get_chapter_id_from_url(ch.url)
        content = get_chapter_images(ch_id, referer=ch.url)
        
        task = task_map[ch.chapter]
        total_pages = len(content.images)
        progress.update(task, total=total_pages)
        completed_pages = 0

        def on_img_done():
            nonlocal completed_pages
            completed_pages += 1
            progress.update(task, completed=completed_pages, description=f"  ⏳ Ch.{ch.chapter}")

        images = download_images_concurrent(
            content.images,
            max_workers=max_img_workers,
            on_image_downloaded=on_img_done,
            config=config,
        )
        export_chapter(
            images, output_dir, manga.title, ch.chapter,
            fmt=fmt, delete_after=delete_images, config=config,
        )
        return ch.chapter, len(images)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        # Create all tasks upfront
        task_map = {}
        for ch in sel_chapters:
            t = progress.add_task(f"  ⏳ Ch.{ch.chapter}", total=100)
            task_map[ch.chapter] = t

        # Submit all chapters to the executor
        with ThreadPoolExecutor(max_workers=max_ch_workers) as executor:
            fut_map = {
                executor.submit(_dl_one_chapter, ch): ch
                for ch in sel_chapters
            }

            for fut in as_completed(fut_map):
                ch = fut_map[fut]
                task = task_map[ch.chapter]
                try:
                    ch_num, img_count = fut.result()
                    total_imgs += img_count
                    progress.update(task, description=f"  ✓ Ch.{ch.chapter}")
                except Exception as e:
                    progress.update(task, description=f"  ✗ Ch.{ch.chapter} — {e}")

    console.print(f"\n[green]✅ Downloaded {len(sel_chapters)} chapters ({total_imgs} pages) in [bold]{fmt}[/bold] format![/green]")

    # Record in history
    History().add(
        manga_id=manga.id,
        manga_title=manga.title,
        manga_slug=manga.slug,
        chapter_range=f"{sel_chapters[0].chapter}-{sel_chapters[-1].chapter}",
        chapter_count=len(sel_chapters),
        export_format=fmt,
        output_path=str(output_dir),
    )


# ── History Command ─────────────────────────────────────────────────────

@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of entries"),
):
    """📋 View download history."""
    h = History()
    entries = h.get_all(limit)
    if not entries:
        console.print("[yellow]No download history yet.[/yellow]")
        raise typer.Exit(0)

    table = Table("Title", "Chapters", "Format", "Date", "Status", box=ROUNDED)
    for e in entries:
        status_icon = "✅" if e.status == "success" else "❌"
        table.add_row(
            e.manga_title,
            e.chapter_range,
            e.export_format,
            e.timestamp[:19] if e.timestamp else "—",
            f"{status_icon} {e.status}",
        )
    console.print(table)


# ── Settings Command ────────────────────────────────────────────────────

@app.command()
def settings(
    show: bool = typer.Option(False, "--show", "-s", help="Show current settings"),
    set_key: Optional[str] = typer.Option(None, "--set", help="Setting key (e.g. output_dir)"),
    value: Optional[str] = typer.Option(None, "--value", "-v", help="Value to set"),
):
    """⚙️ View or edit settings."""
    config = _get_config()

    if show:
        settings_table = Table("Setting", "Value", box=ROUNDED, title="Current Settings")
        settings_table.add_row("output_dir", str(config.output_dir))
        settings_table.add_row("default_format", config.default_format)
        settings_table.add_row("max_concurrent_chapters", str(config.download.max_concurrent_chapters))
        settings_table.add_row("max_concurrent_downloads", str(config.download.max_concurrent_downloads))
        settings_table.add_row("max_retries", str(config.download.max_retries))
        settings_table.add_row("delete_images_after_export", str(config.quality.delete_images_after_export))
        settings_table.add_row("gui.theme", config.gui.theme)
        console.print(settings_table)
        return

    if set_key and value is not None:
        # Map to config fields
        key_map = {
            "output_dir": ("output_dir",),
            "default_format": ("default_format",),
            "theme": ("gui", "theme"),
            "max_concurrent": ("download", "max_concurrent_chapters"),
            "max_retries": ("download", "max_retries"),
            "delete_images": ("quality", "delete_images_after_export"),
        }
        if set_key in key_map:
            parts = key_map[set_key]
            if len(parts) == 1:
                setattr(config, parts[0], value)
            elif len(parts) == 2:
                section = getattr(config, parts[0])
                setattr(section, parts[1], type(getattr(section, parts[1]))(value))
            config.save()
            console.print(f"[green]✓ Set {set_key} = {value}[/green]")
        else:
            valid = ", ".join(key_map)
            console.print(f"[red]Unknown key. Valid: {valid}[/red]")
        return

    console.print("[yellow]Use --show to view or --set KEY --value VAL to change.[/yellow]")


# ── Interactive Shell ──────────────────────────────────────────────────

@app.command()
def interactive():
    """🎮 Launch the interactive menu-driven shell."""
    from mangataro.interactive import run_interactive
    run_interactive()


# ── Entry Point ─────────────────────────────────────────────────────────

def main():
    """Entry point for the CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
