"""MangaTaro Interactive Shell — Rich menu-driven interface."""

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.box import ROUNDED

from mangataro.config import Config
from mangataro.engine import (
    get_manga_info, get_chapter_list, get_chapters_rev,
    get_chapter_images, get_chapter_id_from_url,
    download_images_concurrent,
    extract_slug,
)
from mangataro.search import search_manga
from mangataro.export import export_chapter, EXPORT_FORMATS
from mangataro.history import History

console = Console()


# ── Helpers ─────────────────────────────────────────────────────────────

def _get_config() -> Config:
    return Config.load()


def _fmt_status(status: str) -> str:
    if status == "Ongoing":
        return "🟢 Ongoing"
    elif status == "Completed":
        return "🔴 Completed"
    return f"🟡 {status}"


def _parse_chapters(text: str) -> set[float]:
    """Parse chapter input like '1,4,7-9' into a set of numbers."""
    nums: set[float] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                s, e = part.split("-", 1)
                nums.update(range(int(s), int(e) + 1))
            except ValueError:
                pass
        else:
            try:
                nums.add(int(part))
            except ValueError:
                pass
    return nums


def _get_groups(chapters) -> dict[str, int]:
    """Get group names and their chapter counts."""
    groups = {}
    for ch in chapters:
        g = ch.group_name
        if g:
            groups[g] = groups.get(g, 0) + 1
    return groups


# ── Menu Display ───────────────────────────────────────────────────────

def _show_main_menu() -> str:
    console.print()
    console.print(Panel(
        "[bold magenta]📚 MangaTaro Downloader[/bold magenta]\n\n"
        "  [bold]1.[/bold] 🔍  Search manga by name\n"
        "  [bold]2.[/bold] 🔗  Open manga by URL / slug\n"
        "  [bold]3.[/bold] 📋  Download history\n"
        "  [bold]4.[/bold] ⚙️   Settings\n"
        "  [bold]5.[/bold] ❌  Exit",
        title="Main Menu",
        border_style="magenta",
        box=ROUNDED,
    ))
    return Prompt.ask("Select", choices=["1", "2", "3", "4", "5"], default="1")


# ── Download flow (shared by option 1 & 2) ────────────────────────────

def _download_flow(manga, chapters, manga_title: str = ""):
    """Interactive download flow: group filter → chapter selection → parallel export."""
    config = _get_config()
    rev = get_chapters_rev(chapters)

    if not manga_title:
        manga_title = manga.title

    # ── Show groups ──
    groups = _get_groups(chapters)
    use_group_filter = False
    selected_group = None
    if groups:
        console.print("\n[bold]Available groups:[/bold]")
        for g, count in sorted(groups.items()):
            console.print(f"  • [cyan]{g}[/cyan] ({count} chapters)")
        if Confirm.ask("Filter by group?", default=False):
            group_names = list(groups.keys())
            g_choice = Prompt.ask(
                "  Group name",
                choices=group_names,
            )
            selected_group = g_choice
            use_group_filter = True

    # Filter by group if selected
    filtered = rev
    if use_group_filter and selected_group:
        filtered = [c for c in rev if c.group_name == selected_group]
        console.print(f"  → [cyan]{len(filtered)}[/cyan] chapters in group [bold]{selected_group}[/bold]")

    console.print(f"\n[bold]Manga:[/bold] {manga_title}")
    console.print(f"[bold]Chapters available:[/bold] {len(filtered)}")

    # ── Show chapter preview ──
    if filtered:
        ch_table = Table("Idx", "Chapter", "Title", "Group", "Date", box=ROUNDED)
        for i, ch in enumerate(filtered[:20], 1):
            ch_table.add_row(
                str(i), ch.chapter, ch.title or "—",
                ch.group_name or "—",
                ch.date[:10] if ch.date else "—",
            )
        if len(filtered) > 20:
            ch_table.add_row("...", f"... ({len(filtered) - 20} more)", "", "", "")
        console.print(ch_table)

    # ── Chapter selection ──
    choice = Prompt.ask(
        "Download [bold]all[/bold], a [bold]range[/bold] (e.g. [dim]1-10[/dim]), "
        "or [bold]specific[/bold] (e.g. [dim]5,12-15[/dim])?",
        default="all",
    )
    choice = choice.strip().lower()

    if choice == "all":
        sel_chapters = filtered
    else:
        nums = _parse_chapters(choice)
        sel_chapters = [c for c in filtered if c.chapter_num in nums]
        if not sel_chapters:
            console.print("[yellow]No matching chapters found.[/yellow]")
            return

    # ── Format selection ──
    fmt_choice = Prompt.ask(
        "Export format",
        choices=list(EXPORT_FORMATS.keys()),
        default=config.default_format,
    )

    # ── Confirm ──
    if sel_chapters:
        range_str = f"{sel_chapters[0].chapter}-{sel_chapters[-1].chapter}"
    else:
        range_str = "none"
    delete_imgs = Confirm.ask("Delete images after export?", default=config.quality.delete_images_after_export)

    console.print(f"\n[bold]Summary:[/bold] {len(sel_chapters)} chapters  |  Format: [cyan]{fmt_choice}[/cyan]")
    console.print(f"[dim]Parallel: {config.download.max_concurrent_chapters} chapters, "
                  f"{config.download.max_concurrent_images} images/chapter[/dim]")
    if not Confirm.ask("Proceed?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # ── Parallel Download ────────────────────────────────────────────────
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn

    output_dir = Path(config.output_dir)
    total_imgs = 0
    max_ch_workers = config.download.max_concurrent_chapters
    max_img_workers = config.download.max_concurrent_images

    def _dl_one_chapter(ch) -> tuple[str, int]:
        """Download one chapter (images concurrently). Returns (chapter_num, image_count)."""
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
            fmt=fmt_choice, delete_after=delete_imgs, config=config,
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

    console.print(f"\n[green]✅ Downloaded {len(sel_chapters)} chapters ({total_imgs} pages) as [bold]{fmt_choice}[/bold]![/green]")

    # Record in history
    try:
        History().add(
            manga_id=manga.id,
            manga_title=manga_title,
            manga_slug=manga.slug,
            chapter_range=range_str,
            chapter_count=len(sel_chapters),
            export_format=fmt_choice,
            output_path=str(output_dir),
        )
    except Exception:
        pass

    # Offer to open output folder
    output_path = output_dir / manga_title
    if output_path.exists() and Confirm.ask("Open output folder?", default=False):
        import subprocess, platform
        subprocess.run(["explorer", str(output_path.resolve())] if platform.system() == "Windows" else ["open", str(output_path)])


# ── Actions ─────────────────────────────────────────────────────────────

def _action_search():
    """Search manga by name, show details, then offer download."""
    query = Prompt.ask("\n[bold cyan]Search manga[/bold cyan]")
    if not query:
        return

    with console.status(f"Searching for [bold]{query}[/bold]..."):
        result = search_manga(query)

    if not result.results:
        console.print("[yellow]No results found.[/yellow]")
        return

    # Show results as a table
    table = Table(
        "Idx", "Title", "Type", "Status", "Chapters",
        box=ROUNDED, title=f"Results for \"{result.query}\" ({result.count})",
    )
    for i, m in enumerate(result.results, 1):
        table.add_row(
            str(i),
            f"[cyan]{m.title}[/cyan]",
            m.type or "—",
            _fmt_status(m.status) if m.status else "—",
            str(m.chapter_count) if m.chapter_count else "—",
        )
    console.print(table)

    # Ask if user wants to see details
    if not Confirm.ask("\nView details of a result?", default=False):
        return

    choice = IntPrompt.ask(
        "Enter number",
        choices=[str(i) for i in range(1, len(result.results) + 1)],
        show_choices=False,
    )
    selected = result.results[choice - 1]
    slug = extract_slug(selected.permalink)

    # Show info
    with console.status(f"Fetching info for [bold]{slug}[/bold]..."):
        manga = get_manga_info(slug)

    if not manga.title:
        console.print("[red]✗ Manga not found.[/red]")
        return

    # Build detail panel
    title_str = manga.title
    if manga.original_title:
        title_str += f" [dim]({manga.original_title})[/dim]"

    lines = [
        f"[bold magenta]{title_str}[/bold magenta]",
        "",
        f"[cyan]Status:[/cyan] {_fmt_status(manga.status)}  "
        f"[cyan]Type:[/cyan] {manga.type}  "
        f"[cyan]Views:[/cyan] {manga.views}",
        f"[cyan]Authors:[/cyan] {', '.join(manga.authors) if manga.authors else 'N/A'}  "
        f"[cyan]Chapters:[/cyan] {manga.total_chapters}",
    ]
    if manga.mal_score:
        lines.append(
            f"[yellow]MAL:[/yellow] Score {manga.mal_score}  "
            f"Rank #{manga.mal_rank}  Pop #{manga.mal_popularity}  "
            f"Members {manga.mal_members}"
        )
    if manga.genres:
        lines.append("")
        lines.append(f"[bold]Genres:[/bold] {' • '.join(f'[cyan]{g}[/cyan]' for g in manga.genres)}")
    if manga.description:
        lines.append("")
        lines.append(f"[dim]{manga.description[:400]}[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title="📚 Manga Info",
        border_style="magenta",
        box=ROUNDED,
    ))

    # Fetch chapters
    with console.status(f"Fetching chapter list..."):
        chapters = get_chapter_list(manga.id, manga.slug)

    console.print(f"\n[bold]Chapters:[/bold] {len(chapters)} total")

    # Now offer download flow
    if Confirm.ask("\n⬇️  Download from this manga?", default=True):
        _download_flow(manga, chapters)


def _action_info(slug: str = ""):
    """Show manga info and enter download flow."""
    if not slug:
        url_or_slug = Prompt.ask("\n[bold cyan]Manga URL or slug[/bold cyan]")
        if not url_or_slug:
            return
        slug = extract_slug(url_or_slug)

    with console.status(f"Fetching info for [bold]{slug}[/bold]..."):
        manga = get_manga_info(slug)

    if not manga.title:
        console.print("[red]✗ Manga not found.[/red]")
        return

    # Build detail panel
    title_str = manga.title
    if manga.original_title:
        title_str += f" [dim]({manga.original_title})[/dim]"

    lines = [
        f"[bold magenta]{title_str}[/bold magenta]",
        "",
        f"[cyan]Status:[/cyan] {_fmt_status(manga.status)}  "
        f"[cyan]Type:[/cyan] {manga.type}  "
        f"[cyan]Views:[/cyan] {manga.views}",
        f"[cyan]Authors:[/cyan] {', '.join(manga.authors) if manga.authors else 'N/A'}  "
        f"[cyan]Chapters:[/cyan] {manga.total_chapters}",
    ]
    if manga.mal_score:
        lines.append(
            f"[yellow]MAL:[/yellow] Score {manga.mal_score}  "
            f"Rank #{manga.mal_rank}  Pop #{manga.mal_popularity}  "
            f"Members {manga.mal_members}"
        )
    if manga.genres:
        lines.append("")
        lines.append(f"[bold]Genres:[/bold] {' • '.join(f'[cyan]{g}[/cyan]' for g in manga.genres)}")
    if manga.description:
        lines.append("")
        lines.append(f"[dim]{manga.description[:400]}[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title="📚 Manga Info",
        border_style="magenta",
        box=ROUNDED,
    ))

    # Fetch and show chapters
    chapters = []
    with console.status(f"Fetching chapter list..."):
        chapters = get_chapter_list(manga.id, manga.slug)

    console.print(f"\n[bold]Chapters:[/bold] {len(chapters)} total")

    # Show group info
    groups = _get_groups(chapters)
    if groups:
        console.print("[dim]Groups:[/dim] " + " · ".join(
            f"[cyan]{g}[/cyan] ({c})" for g, c in sorted(groups.items())
        ))

    # Show chapter preview table
    rev = get_chapters_rev(chapters)
    if rev:
        ch_table = Table("Idx", "Chapter", "Title", "Group", "Date", box=ROUNDED)
        for i, ch in enumerate(rev[:20], 1):
            ch_table.add_row(
                str(i), ch.chapter, ch.title or "—",
                ch.group_name or "—",
                ch.date[:10] if ch.date else "—",
            )
        if len(rev) > 20:
            ch_table.add_row("...", f"... ({len(rev) - 20} more)", "", "", "")
        console.print(ch_table)

    # Enter download flow
    if Confirm.ask("\n⬇️  Download chapters?", default=True):
        _download_flow(manga, chapters)


def _action_history():
    """View download history."""
    h = History()
    entries = h.get_all(20)
    if not entries:
        console.print("[yellow]No download history yet.[/yellow]")
        return

    table = Table("Title", "Chapters", "Format", "Date", "Status", box=ROUNDED)
    for e in entries:
        status_icon = "✅" if e.status == "success" else "❌"
        table.add_row(
            e.manga_title or "—",
            e.chapter_range or "—",
            e.export_format or "—",
            e.timestamp[:19] if e.timestamp else "—",
            f"{status_icon} {e.status}",
        )
    console.print(table)

    if entries and Confirm.ask("Clear history?", default=False):
        h.clear()
        console.print("[green]✓ History cleared.[/green]")


def _action_settings():
    """Interactive settings editor."""
    config = _get_config()

    console.print(Panel(
        "[bold yellow]⚙️ Settings[/bold yellow]\n\n"
        "  [bold]1.[/bold] Output directory    [dim]→[/dim] [cyan]{0}[/cyan]\n"
        "  [bold]2.[/bold] Default format       [dim]→[/dim] [cyan]{1}[/cyan]\n"
        "  [bold]3.[/bold] Max concurrent ch.   [dim]→[/dim] [cyan]{2}[/cyan]\n"
        "  [bold]4.[/bold] Max retries          [dim]→[/dim] [cyan]{3}[/cyan]\n"
        "  [bold]5.[/bold] Delete images        [dim]→[/dim] [cyan]{4}[/cyan]\n"
        "  [bold]6.[/bold] GUI theme            [dim]→[/dim] [cyan]{5}[/cyan]\n"
        "  [bold]7.[/bold] ← Back".format(
            config.output_dir,
            config.default_format,
            config.download.max_concurrent_chapters,
            config.download.max_retries,
            config.quality.delete_images_after_export,
            config.gui.theme,
        ),
        title="Settings",
        border_style="yellow",
        box=ROUNDED,
    ))

    choice = Prompt.ask("Edit setting", choices=["1", "2", "3", "4", "5", "6", "7"], default="7")
    if choice == "7":
        return

    key_map = {
        "1": ("output_dir",),
        "2": ("default_format", list(EXPORT_FORMATS.keys())),
        "3": ("download.max_concurrent_chapters",),
        "4": ("download.max_retries",),
        "5": ("quality.delete_images_after_export", ["true", "false"]),
        "6": ("gui.theme", ["dark", "light"]),
    }

    key, *extra = key_map[choice]
    valid_values = extra[0] if extra else None

    if valid_values:
        new_val = Prompt.ask(f"  [bold]{key}[/bold]", choices=valid_values)
    else:
        new_val = Prompt.ask(f"  [bold]{key}[/bold]")

    # Apply
    if "." in key:
        section, attr = key.split(".", 1)
        if hasattr(config, section):
            s = getattr(config, section)
            if hasattr(s, attr):
                current = getattr(s, attr)
                if isinstance(current, bool):
                    setattr(s, attr, new_val.lower() in ("1", "true", "yes"))
                elif isinstance(current, int):
                    setattr(s, attr, int(new_val))
                else:
                    setattr(s, attr, new_val)
    else:
        setattr(config, key, new_val)

    config.save()
    console.print(f"[green]✓ {key} = {new_val}[/green]")


# ── Main Loop ──────────────────────────────────────────────────────────

def run_interactive():
    """Run the interactive shell."""
    console.print()
    console.print(Panel(
        "[bold magenta]📚 Welcome to MangaTaro Downloader[/bold magenta]\n"
        "[dim]Download and manage manga from MangaTaro.org[/dim]",
        border_style="magenta",
        box=ROUNDED,
    ))

    while True:
        try:
            choice = _show_main_menu()

            if choice == "1":
                _action_search()
            elif choice == "2":
                _action_info()
            elif choice == "3":
                _action_history()
            elif choice == "4":
                _action_settings()
            elif choice == "5":
                console.print("[bold magenta]Goodbye! 📚[/bold magenta]")
                break

            if choice in ("1", "2", "3", "4"):
                Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Goodbye![/yellow]")
            break


if __name__ == "__main__":
    run_interactive()
