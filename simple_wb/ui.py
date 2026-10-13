from datetime import date
from typing import Dict, List, Optional
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from .models import WordEntry, PartOfSpeech, Gender
from .dictionary import DictSearchResult

console = Console()

# Color palette
COLOR_DER   = "bold #3b82f6"     # der   → насичений кобальтовий синій (Royal Blue)
COLOR_DIE   = "bold #f43f5e"     # die   → виразний коралово-рожевий (Rose)
COLOR_DAS   = "bold #10b981"     # das   → смарагдово-зелений (Emerald)
COLOR_VERB  = "bold #f59e0b"     # verb  → теплий бурштиновий / золотий (Amber)
COLOR_ADJ   = "bold #a855f7"     # adj   → фіолетовий (Purple)
COLOR_OTHER = "bold #06b6d4"     # other → чистий ціан / бірюза (Cyan)
COLOR_AUTO  = "italic #94a3b8"   # ~ маркер автовизначення (приглушений курсив)
COLOR_SEP   = "#64748b"          # separator (—) графітовий сланець
COLOR_TRANS = "#e2e8f0"          # translation → м'який світло-сірий
COLOR_ID    = "#475569"          # #id → приглушений, але чітко читабельний графіт


def _gender_color(gender: Gender) -> str:
    if gender == Gender.MASCULINE:
        return COLOR_DER
    if gender == Gender.FEMININE:
        return COLOR_DIE
    return COLOR_DAS


def format_day_header(target_date: date) -> str:
    today = date.today()
    delta = (today - target_date).days
    formatted = target_date.strftime("%d %b %Y")
    if target_date.year == today.year:
        formatted = target_date.strftime("%d %b")
    if delta == 0:
        return f"Today, {formatted}"
    if delta == 1:
        return f"Yesterday, {formatted}"
    return formatted


def render_entry_text(entry: WordEntry) -> Text:
    """Render one word entry as a colored Rich Text line."""
    text = Text()

    # #id
    id_str = f"#{entry.id:02d}" if entry.id is not None else "   "
    text.append(f"{id_str:>4} ", style=COLOR_ID)

    # auto-detection marker (~) or space
    if entry.auto_detected:
        text.append("~", style=COLOR_AUTO)
    else:
        text.append(" ")

    # Article / POS tag
    if entry.gender:
        art = entry.article
        text.append(f"{art:<3} ", style=_gender_color(entry.gender))
    elif entry.pos == PartOfSpeech.VERB:
        text.append("verb", style=COLOR_VERB)
    elif entry.pos == PartOfSpeech.ADJ:
        text.append("adj ", style=COLOR_ADJ)
    elif entry.pos == PartOfSpeech.ADV:
        text.append("adv ", style=COLOR_OTHER)
    elif entry.pos == PartOfSpeech.PHRASE:
        text.append("phr ", style=COLOR_OTHER)
    else:
        text.append("    ")

    text.append(" ")

    # German word & forms display
    if entry.pos == PartOfSpeech.VERB:
        # Partizip II
        if entry.verb_form == "p2" and entry.lemma:
            text.append(entry.german, style="bold white")
            if entry.hilfsverb:
                hv_color = "bright_blue" if entry.hilfsverb == "haben" else "bright_green"
                text.append(f"  [{entry.hilfsverb}]", style=f"dim {hv_color}")
            text.append(f"  (P2 of {entry.lemma})", style="dim cyan")
        # Präteritum
        elif entry.verb_form == "prat" and entry.lemma:
            text.append(entry.german, style="bold white")
            if entry.hilfsverb:
                hv_color = "bright_blue" if entry.hilfsverb == "haben" else "bright_green"
                text.append(f"  [{entry.hilfsverb}]", style=f"dim {hv_color}")
            text.append(f"  (Prät of {entry.lemma})", style="dim cyan")
        # Infinitive verb
        else:
            if entry.is_separable and entry.verb_prefix and entry.german.startswith(entry.verb_prefix):
                stem = entry.german[len(entry.verb_prefix):]
                text.append(entry.verb_prefix, style="bold yellow")
                text.append("|", style="dim")
                text.append(stem, style="bold white")
            else:
                text.append(entry.german, style="bold white")

            if entry.hilfsverb:
                hv_color = "bright_blue" if entry.hilfsverb == "haben" else "bright_green"
                text.append(f"  [{entry.hilfsverb}]", style=f"dim {hv_color}")

            # Show principal forms: (fuhr, ist gefahren) or (machte, hat gemacht)
            if entry.praeteritum and entry.partizip2:
                aux = "ist" if entry.hilfsverb == "sein" else "hat"
                text.append(f"  ({entry.praeteritum}, {aux} {entry.partizip2})", style="dim")

    elif entry.pos == PartOfSpeech.NOUN:
        text.append(entry.german, style="bold white")
        if entry.plural:
            text.append(f", -{entry.plural}", style="dim")

    else:
        text.append(entry.german, style="bold white")

    # Separator + translation
    if entry.translation:
        text.append("  —  ", style=COLOR_SEP)
        text.append(entry.translation, style=COLOR_TRANS)

    return text


def print_word_added(entry: WordEntry):
    """Print confirmation line immediately after a word is added."""
    row = render_entry_text(entry)
    reason_text = ""
    if entry.auto_detected and entry.detection_reason:
        reason_text = f"  [dim]({entry.detection_reason})[/dim]"
    console.print(Text.assemble(Text(" + ", style="bold green"), row), end="")
    if reason_text:
        console.print(reason_text, highlight=False)
    else:
        console.print()


def print_word_updated(entry: WordEntry):
    """Print confirmation line immediately after a word is edited."""
    row = render_entry_text(entry)
    console.print(Text.assemble(Text(" ~ ", style="bold yellow"), row))


def render_words_by_day(grouped_words: Dict[date, List[WordEntry]]):
    """Print word list grouped by day."""
    if not grouped_words or all(len(w) == 0 for w in grouped_words.values()):
        console.print("[dim]No words yet. Add your first one (e.g.: das Kind - child)[/dim]\n")
        return

    for target_date in sorted(grouped_words.keys()):
        words = grouped_words[target_date]
        if not words:
            continue
        header = format_day_header(target_date)
        count_str = f"{len(words)} word{'s' if len(words) != 1 else ''}"
        console.print(f"\n[dim]───[/dim] [bold yellow]{header}[/] [dim]·  {count_str}  {'─' * 40}[/dim]")
        for w in words:
            console.print(render_entry_text(w))
    console.print()


def render_dict_search_results(results: List[DictSearchResult], translations: Dict[str, str]):
    """Print dictionary search results as a numbered list."""
    if not results:
        console.print("[dim]No matches found in offline dictionary.[/dim]\n")
        return

    console.print(f"\n[bold yellow]Dictionary search results[/bold yellow] [dim]({len(results)} matches):[/dim]")
    for i, r in enumerate(results, start=1):
        line = Text()
        line.append(f"[{i:>2}] ", style="bold cyan")

        # POS / article
        if r.gender:
            line.append(f"{r.gender.article:<3} ", style=_gender_color(r.gender))
        elif r.pos == PartOfSpeech.VERB:
            line.append("verb ", style=COLOR_VERB)
        elif r.pos == PartOfSpeech.ADJ:
            line.append("adj  ", style=COLOR_ADJ)
        else:
            line.append("     ")

        # Word display (separable split)
        if "|" in r.display_german:
            pfx, stem = r.display_german.split("|", 1)
            line.append(pfx, style="bold yellow")
            line.append("|", style="dim")
            line.append(stem, style="bold white")
        else:
            line.append(r.word, style="bold white")

        # Forms / Extra info
        if r.pos == PartOfSpeech.NOUN and r.extra:
            line.append(f", -{r.extra}", style="dim")
        elif r.pos == PartOfSpeech.VERB and r.verb_info:
            vi = r.verb_info
            if vi.hilfsverb:
                hv_color = "bright_blue" if vi.hilfsverb == "haben" else "bright_green"
                line.append(f"  [{vi.hilfsverb}]", style=f"dim {hv_color}")
            if vi.praeteritum and vi.partizip2:
                aux = "ist" if vi.hilfsverb == "sein" else "hat"
                line.append(f"  ({vi.praeteritum}, {aux} {vi.partizip2})", style="dim")

        # Matched form note if found via inflected form (e.g. ← ging, Prät)
        if getattr(r, "matched_form", None):
            line.append(f"  (← {r.matched_form})", style="dim cyan")

        # Translation gloss
        trans = translations.get(r.word)
        if trans:
            line.append("  —  ", style=COLOR_SEP)
            line.append(trans, style=COLOR_TRANS)

        console.print(line)

    console.print("\n[dim]Quick add: type [bold green]+1[/] (or [bold green]+1 custom translation[/]) to add to your list[/dim]\n")


def print_help():
    help_text = r"""
[bold yellow]Commands:[/bold yellow]
  [cyan]:all[/cyan]  [cyan]:list[/cyan]       Show all saved words
  [cyan]:today[/cyan]             Show today's words
  [cyan]:edit <id>[/cyan]         Edit word by id ([dim]:edit 3[/dim] or [dim]:e 3 das Kind - new translation[/dim])
  [cyan]:del <id>[/cyan]          Delete word by id  ([dim]:del 3[/dim])
  [cyan]:s <query>[/cyan]         Search saved words (by German, translation, or lemma)
  [cyan]:dict <query>[/cyan]      Dictionary lookup or wildcard search ([dim]:dict *machen[/dim], [dim]:dict *tür[/dim])
  [cyan]:stats[/cyan]             Vocabulary statistics
  [cyan]:clear[/cyan]             Clear screen
  [cyan]:q[/cyan]  [cyan]:exit[/cyan]          Quit

[bold yellow]Input syntax:[/bold yellow]
  [bold bright_blue]der[/] Tisch - table          explicit article
  [bold magenta]die[/] Zeitung - newspaper     explicit article
  [bold bright_green]das[/] Kind - child           explicit article
  Kind - child               [yellow]~[/][bright_green]das[/] auto-detected via offline dict
  Zeitung                    auto-detects gender + auto-translates [white]newspaper[/white]

  [bold yellow]Fast verb input (> Partizip II, >> Präteritum):[/bold yellow]
  machen > gemacht >> machte - to do       stores all 3 forms in one go
  auf|stehen > aufgestanden >> stand auf    separable verb with forms
  fahren > gefahren >> fuhr                 auto-translates if translation omitted

  [bold yellow]Single verb forms:[/bold yellow]
  fahren - to drive          [yellow]~verb[/] fahren [dim bright_green]\[sein][/] (fuhr, ist gefahren)
  gefahren - driven          [yellow]~verb[/] gefahren [dim bright_green]\[sein][/] [dim cyan](P2 of fahren)[/]
  fuhr - drove               [yellow]~verb[/] fuhr [dim bright_green]\[sein][/] [dim cyan](Prät of fahren)[/]

  [bold yellow]Wildcard dictionary search & Quick Add:[/bold yellow]
  :dict *machen              finds aufmachen, anmachen, zumachen, mitmachen...
  +1                         adds match #1 with translation to your vocabulary
  +1 custom translation      adds match #1 with your custom translation
  +aufmachen                 directly look up and add 'aufmachen' with translation
"""
    console.print(Panel(help_text.strip(), title="[bold]simple-wb help[/bold]", border_style="dim"))
