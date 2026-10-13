import re
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style


GERMAN_STYLE = Style.from_dict(
    {
    # ── Артиклі (традиційне німецьке тріо з максимальною різницею) ──
    "der": "#3b82f6 bold",        # Яскравий кобальтовий синій (Royal Blue)
    "die": "#f43f5e bold",        # Виразний коралово-рожевий / троянда (Rose-500)
    "das": "#10b981 bold",        # Насичений смарагдовий (Emerald-500)

    # ── Частини мови (POS) ──
    "nomen": "#06b6d4 bold",      # Чистий ціан / бірюза (Cyan-500)
    "verb": "#f59e0b bold",       # Теплий бурштиновий (Amber-500)
    "adj": "#a855f7 bold",        # Глибокий фіолетовий (Purple-500)
    "prefix": "#e879f9 bold",     # Світла фуксія / маджента (Fuchsia-400)

    # ── Службові елементи інтерфейсу ──
    "op": "#94a3b8 bold",         # Сталевий світло-сірий (Slate-400, більше не зливається з der/cmd)
    "cmd": "#38bdf8 bold",        # Небесно-блакитний (Sky-400, фірмовий для Azure)
    "add": "#4ade80 bold",        # Салатовий / лайм (відрізняється від смарагдового das)
    "separator": "#64748b bold",  # Приглушений графіт / сланець
    "auto": "#94a3b8 italic",     # Приглушений курсив (не перебиває дієслова verb)

    # ── Текст слів ──
    "word": "#ffffff bold",       # Чистий яскравий білий
    "translation": "#e2e8f0",     # М'який білий (без жирного шрифту для кращої ієрархії)   # Auto-suggestion
    }
)


class GermanInputLexer(Lexer):
    """
    Custom lexer for real-time syntax highlighting in REPL.
    Supports articles, POS prefixes, form operators (> and >>), quick-add (+), and separators.
    """

    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]
            tokens = []

            # Commands starting with ':'
            if line.startswith(":"):
                parts = line.split(maxsplit=1)
                tokens.append(("class:cmd", parts[0]))
                if len(parts) > 1:
                    tokens.append(("", " " + parts[1]))
                return tokens

            # Quick-add starting with '+' (e.g. +1 or +aufmachen)
            if line.startswith("+"):
                parts = line.split(maxsplit=1)
                tokens.append(("class:add", parts[0]))
                if len(parts) > 1:
                    tokens.append(("", " " + parts[1]))
                return tokens

            # Separator (- or — or : or =)
            sep_match = re.search(r"(\s*[-—–:=]\s*)", line)
            if sep_match:
                left_str = line[: sep_match.start()]
                sep_str = sep_match.group(1)
                right_str = line[sep_match.end() :]
            else:
                left_str = line
                sep_str = ""
                right_str = ""

            # Parse left part with operators > and >>
            # Split tokens by whitespace but keep > and >> intact
            words = left_str.split(" ")
            for i, w in enumerate(words):
                w_lower = w.lower()
                if w in (">", ">>"):
                    tokens.append(("class:op", w))
                elif w_lower == "der":
                    tokens.append(("class:der", w))
                elif w_lower == "die":
                    tokens.append(("class:die", w))
                elif w_lower == "das":
                    tokens.append(("class:das", w))
                elif w_lower in ("verb", "v", "p2", "partizip", "prat", "prät", "pret"):
                    tokens.append(("class:verb", w))
                elif w_lower in ("adj", "adjektiv", "a"):
                    tokens.append(("class:adj", w))
                elif w_lower in ("nomen", "noun", "n"):
                    tokens.append(("class:nomen", w))
                else:
                    if any(w_lower.endswith(s) for s in ("ung", "heit", "keit", "schaft", "tion")):
                        tokens.append(("class:die", w))
                    elif w_lower.endswith(("chen", "lein", "ment", "um")):
                        tokens.append(("class:das", w))
                    elif any(w_lower.endswith(s) for s in ("ismus", "ling", "ist")):
                        tokens.append(("class:der", w))
                    elif not (w and w[0].isupper()) and w_lower.endswith(("en", "eln", "ern")):
                        tokens.append(("class:verb", w))
                    elif not (w and w[0].isupper()) and any(w_lower.endswith(s) for s in ("lich", "isch", "ig", "bar")):
                        tokens.append(("class:adj", w))
                    else:
                        tokens.append(("class:word", w))

                if i < len(words) - 1:
                    tokens.append(("", " "))

            # Separator
            if sep_str:
                tokens.append(("class:separator", sep_str))

            # Translation
            if right_str:
                tokens.append(("class:translation", right_str))

            return tokens

        return get_line
