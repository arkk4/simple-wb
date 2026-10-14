import base64
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import date
from typing import List, Dict, Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from .storage import WordStorage
from .dictionary import GermanDictionary, DictSearchResult
from .parser import InputParser
from .translator import WordTranslator
from .syntax import GermanInputLexer, GERMAN_STYLE
from .models import PartOfSpeech, WordEntry
from .ui import (
    console,
    render_words_by_day,
    print_word_added,
    print_word_updated,
    print_help,
    render_entry_text,
    render_dict_search_results,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LOGO_PNG_PATH = REPO_ROOT / "public" / "logo.png"
LOGO_SVG_PATH = REPO_ROOT / "public" / "logo.svg"
LOGO_PATH = LOGO_PNG_PATH
VERSION = "1.0.0"
APP = "wbuch"


def _is_iterm2() -> bool:
    return ("iTerm" in os.environ.get("TERM_PROGRAM", "") or
            "iTerm" in os.environ.get("LC_TERMINAL", ""))


_logo_cache: Optional[str] = None


def _logo_png_b64() -> Optional[str]:
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache
    if LOGO_PNG_PATH.exists():
        try:
            _logo_cache = base64.b64encode(LOGO_PNG_PATH.read_bytes()).decode("ascii")
            return _logo_cache
        except OSError:
            pass
    if not LOGO_SVG_PATH.exists():
        return None
    try:
        svg_bytes = LOGO_SVG_PATH.read_bytes()
        r = subprocess.run(["rsvg-convert", "-w", "128", "-f", "png"],
                           input=svg_bytes, capture_output=True, timeout=5)
        if r.returncode == 0 and r.stdout:
            _logo_cache = base64.b64encode(r.stdout).decode("ascii")
            return _logo_cache
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def print_startup_logo() -> None:
    if not _is_iterm2():
        return
    logo_b64 = _logo_png_b64()
    if logo_b64:
        nb = base64.b64encode(b"logo").decode()
        esc = f"\033]1337;File=name={nb};width=4;height=2;preserveAspectRatio=1;inline=1:{logo_b64}\a"
        sys.stdout.write(esc + "\n")
        sys.stdout.flush()


def get_history_path() -> str:
    new_h = os.path.join(os.path.expanduser("~"), ".wbuch_history")
    old_h = os.path.join(os.path.expanduser("~"), ".simple_wb_history")
    return new_h if os.path.exists(new_h) or not os.path.exists(old_h) else old_h


def run_repl():
    storage = WordStorage()
    dictionary = GermanDictionary()
    translator = WordTranslator()
    parser = InputParser(dictionary=dictionary, translator=translator)

    last_search_results: List[DictSearchResult] = []
    last_search_translations: Dict[str, str] = {}

    # Greeting banner
    print_startup_logo()
    console.print(
        f"\n[bold yellow]📖 wbuch[/bold yellow]  "
        f"[dim]fast German vocabulary input & dictionary (v{VERSION})[/dim]"
    )
    console.print(
        "[dim]colors: [/dim]"
        "[bold bright_blue]der[/] [bold magenta]die[/] [bold bright_green]das[/] "
        "[bold yellow]verb[/] [bold medium_purple]adj[/]"
        "[dim]  ·  [yellow]~[/] = auto-detected  ·  [cyan]:h[/cyan] help  [cyan]:q[/cyan] quit[/dim]"
    )

    # Show recent words (last 3 days)
    grouped = storage.get_words_grouped_by_day(limit_days=3)
    if grouped:
        render_words_by_day(grouped)
    else:
        console.print(
            "[dim]No words yet — try: [white]das Kind - child[/white] or [white]machen > gemacht >> machte[/white][/dim]\n"
        )

    session = PromptSession(
        history=FileHistory(get_history_path()),
        auto_suggest=AutoSuggestFromHistory(),
        lexer=GermanInputLexer(),
        style=GERMAN_STYLE,
    )

    while True:
        try:
            user_input = session.prompt("wbuch › ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Tschüss! 👋[/dim]")
            break

        line = user_input.strip()
        if not line:
            continue

        # ──────────────────────────────────────────────
        # 1. Quick Add from dictionary: +1 or +1 custom translation or +aufmachen
        # ──────────────────────────────────────────────
        if line.startswith("+"):
            add_content = line[1:].strip()
            # Case A: +1 or +1 custom translation
            match_num = re.match(r"^(\d+)(?:\s+(.+))?$", add_content)
            if match_num:
                idx = int(match_num.group(1)) - 1
                custom_trans = match_num.group(2)
                if 0 <= idx < len(last_search_results):
                    res = last_search_results[idx]
                    trans = (
                        custom_trans
                        if custom_trans
                        else last_search_translations.get(res.word)
                        or translator.translate(res.word)
                        or ""
                    )
                    # Build input line for parser
                    input_str = f"{res.display_german} - {trans}"
                    entry = parser.parse_line(input_str)
                    if entry:
                        saved = storage.add_word(entry)
                        print_word_added(saved)
                else:
                    console.print(f"[red]Index #{idx + 1} not in last search results (1..{len(last_search_results)}).[/red]")
                continue

            # Case B: just '+' after viewing a single word in :dict
            if not add_content and last_search_results:
                res = last_search_results[0]
                trans = last_search_translations.get(res.word) or translator.translate(res.word) or ""
                input_str = f"{res.display_german} - {trans}"
                entry = parser.parse_line(input_str)
                if entry:
                    saved = storage.add_word(entry)
                    print_word_added(saved)
                continue

            # Case C: +<word> directly adds word with auto-translation
            if add_content:
                entry = parser.parse_line(add_content)
                if entry:
                    saved = storage.add_word(entry)
                    print_word_added(saved)
                continue

        # ──────────────────────────────────────────────
        # 2. Commands (start with :)
        # ──────────────────────────────────────────────
        if line.startswith(":"):
            cmd_parts = line[1:].strip().split(maxsplit=1)
            cmd = cmd_parts[0].lower()
            arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

            if cmd in ("q", "quit", "exit"):
                console.print("[dim]Tschüss! 👋[/dim]")
                break

            elif cmd in ("h", "help", "?"):
                print_help()

            elif cmd in ("all", "list", "ls"):
                render_words_by_day(storage.get_words_grouped_by_day())

            elif cmd in ("today", "t"):
                words = storage.get_words_for_day(date.today())
                if words:
                    render_words_by_day({date.today(): words})
                else:
                    console.print("[dim]No words added today yet.[/dim]")

            elif cmd in ("del", "rm", "delete"):
                if not arg or not arg.isdigit():
                    console.print("[red]Usage: :del <id>[/red]")
                else:
                    wid = int(arg)
                    if storage.delete_word(wid):
                        console.print(f"[green]✓ Word #{wid} deleted.[/green]")
                    else:
                        console.print(f"[red]Word #{wid} not found.[/red]")

            elif cmd in ("e", "edit"):
                # Format 1: :edit <id> <new text>
                # Format 2: :edit <id> (interactive edit with current line pre-filled)
                if not arg:
                    console.print("[red]Usage: :edit <id> [new text][/red]")
                    continue

                edit_parts = arg.split(maxsplit=1)
                if not edit_parts[0].isdigit():
                    console.print("[red]Usage: :edit <id> [new text][/red]")
                    continue

                wid = int(edit_parts[0])
                existing = storage.get_word_by_id(wid)
                if not existing:
                    console.print(f"[red]Word #{wid} not found.[/red]")
                    continue

                if len(edit_parts) > 1:
                    new_line = edit_parts[1]
                else:
                    # Interactive prompt with pre-filled text
                    if existing.gender:
                        default_line = f"{existing.gender.article} {existing.german} - {existing.translation}"
                    elif existing.is_separable:
                        default_line = f"{existing.display_german} - {existing.translation}"
                    else:
                        default_line = f"{existing.german} - {existing.translation}"

                    try:
                        new_line = session.prompt(f"edit #{wid} › ", default=default_line)
                    except (KeyboardInterrupt, EOFError):
                        console.print("[dim]Edit cancelled.[/dim]")
                        continue

                new_entry = parser.parse_line(new_line)
                if new_entry:
                    new_entry.id = wid
                    if storage.update_word(new_entry):
                        print_word_updated(new_entry)
                    else:
                        console.print(f"[red]Failed to update #{wid}.[/red]")

            elif cmd in ("s", "search", "find"):
                if not arg:
                    console.print("[red]Usage: :s <query>[/red]")
                else:
                    results = storage.search(arg)
                    if results:
                        console.print(f"\n[dim]Found {len(results)} result(s) in vocabulary for '{arg}':[/dim]")
                        for w in results:
                            console.print(render_entry_text(w))
                        console.print()
                    else:
                        console.print(f"[dim]No saved words matching '{arg}'.[/dim]")

            elif cmd in ("dict", "d"):
                if not arg:
                    console.print("[red]Usage: :dict <word or *pattern>[/red]")
                    continue

                # Search dictionary (handles exact words, inflected forms, and *wildcards)
                search_matches = dictionary.search_dict(arg, limit=15)
                if not search_matches:
                    single = dictionary.lookup(arg)
                    if single:
                        display = arg
                        if single.pos == PartOfSpeech.NOUN and single.gender:
                            display = f"{single.gender.article} {arg}"
                        search_matches = [
                            DictSearchResult(
                                word=arg,
                                pos=single.pos,
                                gender=single.gender,
                                extra=single.extra,
                                lemma=single.lemma,
                                form=single.verb_info.form if single.verb_info else None,
                                verb_info=single.verb_info,
                                display_german=display,
                            )
                        ]

                if not search_matches:
                    console.print(f"[dim]'{arg}' not found in offline dictionary.[/dim]")
                    continue

                # Fetch translations quickly for search results (instant cache + parallel remote)
                translations = translator.translate_batch([m.word for m in search_matches])
                last_search_results = search_matches
                last_search_translations = translations

                if len(search_matches) > 1 or "*" in arg:
                    render_dict_search_results(search_matches, translations)
                else:
                    # Single result detailed view
                    r = search_matches[0]
                    pos_str = r.pos.value
                    art = f" [bold]{r.gender.article}[/bold]" if r.gender else ""
                    mf_str = f" [dim cyan](← {r.matched_form})[/]" if getattr(r, "matched_form", None) else ""
                    console.print(f"\n[green]dict:[/] [bold]{r.display_german}[/]{mf_str} → {pos_str}{art}")
                    if r.pos == PartOfSpeech.NOUN and r.extra:
                        console.print(f"  Plural:    [dim]-{r.extra}[/dim]")
                    elif r.pos == PartOfSpeech.VERB and r.verb_info:
                        vi = r.verb_info
                        if vi.hilfsverb:
                            hv_color = "bright_blue" if vi.hilfsverb == "haben" else "bright_green"
                            console.print(f"  Hilfsverb: [{hv_color}]{vi.hilfsverb}[/{hv_color}]")
                        aux = "ist" if vi.hilfsverb == "sein" else "hat"
                        p2_disp = f"{aux} {vi.partizip2}" if vi.partizip2 else "-"
                        console.print(f"  Forms:     [dim]{vi.infinitive}, {vi.praeteritum or '-'}, {p2_disp}[/dim]")
                    trans = translations.get(r.word) or translator.translate(r.word)
                    if trans:
                        console.print(f"  Meaning:   [white]{trans}[/white]")
                    console.print("[dim]Type [bold green]+[/] to add this word to your vocabulary[/dim]\n")

            elif cmd == "stats":
                s = storage.get_stats()
                console.print(f"\n[bold]Vocabulary stats:[/bold]")
                console.print(f"  Total words:        [bold green]{s['total']}[/]")
                console.print(f"  Added today:        [bold cyan]{s['today']}[/]")
                console.print(f"  Separable verbs:    [bold yellow]{s.get('separable_verbs', 0)}[/]")
                console.print(f"  Verb forms (P2/Pr): [bold magenta]{s.get('conjugated_verbs', 0)}[/]")
                console.print(f"  By POS:             {s['by_pos']}")
                console.print(f"  By gender:          {s['by_gender']}\n")

            elif cmd in ("clear", "cls"):
                os.system("clear")

            else:
                console.print(f"[red]Unknown command :{cmd} — type :h for help.[/red]")

            continue

        # ──────────────────────────────────────────────
        # 3. Normal word entry
        # ──────────────────────────────────────────────
        entry = parser.parse_line(line)
        if entry is None:
            continue

        saved = storage.add_word(entry)
        print_word_added(saved)


def main():
    run_repl()


if __name__ == "__main__":
    main()
