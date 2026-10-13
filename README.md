# simple-wb (wbuch) 📖

> **Fast, smart CLI REPL tool for learning and collecting German vocabulary.**  
> Features real-time syntax highlighting, offline dictionary auto-detection, auxiliary verb tracking (*haben/sein*), separable verb prefixes (*Trennbare Verben*), conjugation forms (*Partizip II / Präteritum*), wildcard search, auto-translation, and quick-add shortcuts.

![wbuch badge](public/badge.svg)

---

## 🚀 Quick Start

### Prerequisites
Python 3.9+ with `prompt_toolkit` and `rich`:
```bash
pip install prompt_toolkit rich
```

### Launching
Run directly via the executable wrapper:
```bash
./wbuch
# or
cli/wbuch
```
Or with Python:
```bash
PYTHONPATH=. python3 -m simple_wb
```

---

## 🎨 Color Palette & Visual Feedback

Input and entries are color-coded in real time:
- **Blue**: `der` (Masculine)
- **Magenta**: `die` (Feminine)
- **Green**: `das` (Neuter)
- **Amber / Yellow**: `verb` & separable prefixes (`auf|`)
- **Purple**: `adj` (Adjectives)
- **Cyan**: `adv`, `phrase`, `lemma references`
- **Yellow `~` marker**: Indicates properties that were **auto-detected** by the system.

---

## ✍️ Input Syntax

### 1. Nouns (*Substantive*)
| Input | Output | Note |
|---|---|---|
| `das Kind - child` | `#01  das Kind, -Kinder — child` | Explicit article |
| `Kind - child` | `#02 ~das Kind, -Kinder — child` | Auto-detected from 93k offline dictionary |
| `Zeitung - newspaper` | `#03 ~die Zeitung, -Zeitungen — newspaper` | Auto-detected from suffix `-ung` |
| `Auto` | `#04 ~das Auto — car` | Auto-detected gender + auto-translated |

- Plural forms are automatically looked up from the offline dictionary (`-Kinder`, `-Zeitungen`).
- Lowercase noun inputs (`kind - child`) are automatically capitalized (`Kind`).

---

### 2. Verbs (*Verben*), Hilfsverb & 3-Form Syntax

Every German verb is stored with its auxiliary verb (`haben` or `sein`), separable prefix, and principal forms.

#### A. Fast 3-Form Operator Syntax (`>` and `>>`)
Easily record the infinitive, Partizip II, and Präteritum in a single line in **any order**:
- `>` precedes **Partizip II**
- `>>` precedes **Präteritum**

```text
wb › machen > gemacht >> machte - to do
 +  #01 ~verb machen  [haben]  (machte, hat gemacht)  —  to do

wb › machen >> machte > gemacht - to do
 +  #02 ~verb machen  [haben]  (machte, hat gemacht)  —  to do

wb › auf|stehen > aufgestanden >> stand auf - to get up
 +  #03  verb auf|stehen  [sein]  (stand auf, ist aufgestanden)  —  to get up
```
*(Smart disambiguation automatically classifies the forms even if you swap `>` and `>>`!)*

#### B. Infinitive Forms
```text
wb › fahren - to drive
 +  #04 ~verb fahren  [sein]  (fuhr, ist gefahren)  —  to drive
```

#### C. Conjugated Forms (Partizip II & Präteritum)
Entering a conjugated form automatically recognizes its infinitive lemma:
```text
wb › gefahren - driven
 +  #05 ~verb gefahren  [sein]  (P2 of fahren)  —  driven

wb › fuhr - drove
 +  #06 ~verb fuhr  [sein]  (Prät of fahren)  —  drove

wb › aufgestanden - stood up
 +  #07 ~verb aufgestanden  [sein]  (P2 of aufstehen)  —  stood up

wb › stand auf - got up
 +  #08 ~verb stand auf  [sein]  (Prät of aufstehen)  —  got up
```

#### D. Separable Verbs (*Trennbare Verben*)
Explicit pipe notation or automatic prefix detection:
- `auf|machen - to open` → Yellow `auf` + white `machen`
- `aufstehen - to get up` → Auto-detected separable prefix `auf-`

---

### 3. Manual POS Prefixes (Optional)
If a word is rare or you want explicit control:
- `verb laufen - to run`
- `p2 gemacht - done` / `partizip gegessen - eaten`
- `prat lief - ran` / `prät dachte - thought`
- `adj schön - beautiful`
- `adv schnell - quickly`
- `phrase ab und zu - now and then`

---

### 4. Automatic Translation Fallback
If you omit the translation, `simple-wb` will query local cache, MyMemory, and Wiktionary definitions to auto-fill an English gloss:
```text
wb › das Kind
 +  #09  das Kind, -Kinder  —  child

wb › aufmachen
 +  #10 ~verb auf|machen  [haben]  (machte auf, hat aufgemacht)  —  open
```

---

## 🔍 Commands Reference

Commands begin with a colon `:`

| Command | Shortcut | Description |
|---|---|---|
| `:all` | `:list`, `:ls` | Show all saved words grouped by date |
| `:today` | `:t` | Show words added today |
| `:edit <id>` | `:e <id>` | Edit word (interactive pre-filled prompt or inline) |
| `:del <id>` | `:rm <id>` | Delete word by `#id` |
| `:s <query>` | `:find` | Search saved vocabulary (by German, translation, or lemma) |
| `:dict <query>` | `:d` | Look up word or run wildcard search |
| `:stats` | | Vocabulary statistics (total, today, separable, forms) |
| `:clear` | `:cls` | Clear terminal screen |
| `:help` | `:h`, `:?` | Display help panel |
| `:quit` | `:q`, `:exit` | Exit the REPL |

---

## 🔎 Wildcard Dictionary Search & Quick Add

The offline dictionary contains over **124,000 entries** (93k nouns, 8k verbs with forms, 7k adjectives).

### Wildcard Search (`*pattern`)
Use `*` to match prefix, suffix, or substring:
```text
wb › :dict *machen

Dictionary search results (10 matches):
[ 1] verb machen     [haben]  (machte, hat gemacht)       — to make / do
[ 2] verb ab|machen  [haben]  (machte ab, hat abgemacht)  — make a deal
[ 3] verb an|machen  [haben]  (machte an, hat angemacht)  — turn on
[ 4] verb zu|machen  [haben]  (machte zu, hat zugemacht)  — close
[ 5] verb auf|machen [haben]  (machte auf, hat aufgemacht)— open
...
Quick add: type +1 (or +1 custom translation) to add to your list
```

Other search examples:
- `:dict *tür` — all compound words ending in `tür` (*Haustür, Bürotür, Drehtür...*)
- `:dict *haus*` — all words containing `haus`

### Quick Add Shortcuts (`+`)
- **Add from search results**:
  - `+1` — immediately saves item `[ 1]` with its suggested translation.
  - `+1 to open up` — saves item `[ 1]` with your custom translation.
- **Add after single word lookup**:
  - `:dict aufstehen` followed by `+` — adds `aufstehen` immediately.
- **Direct quick-add from prompt**:
  - `+aufmachen` — resolves forms, translates, and saves in one step.

---

## ✏️ Editing Saved Words (`:edit` / `:e`)

### Interactive Edit (Pre-filled Input)
Type `:edit <id>` to open an interactive prompt pre-filled with the current entry text:
```text
wb › :edit 3
edit #3 › das Kind - child  [cursor is placed inside the prompt; edit and press Enter]
 ~ #03  das Kind, -Kinder  —  a young child
```

### Direct Inline Edit
Replace in one command:
```text
wb › :edit 3 das Kind - young child
 ~ #03  das Kind, -Kinder  —  young child
```

---

## 🗄️ Architecture & Storage

All data is stored locally in the `data/` directory:
- **`data/words.db`**: User vocabulary SQLite database (`words` table with columns: `id`, `german`, `translation`, `pos`, `gender`, `plural`, `hilfsverb`, `verb_prefix`, `verb_form`, `lemma`, `praeteritum`, `partizip2`, `created_at`).
- **`data/dictionary.db`**: Bundled offline dictionary SQLite database containing:
  - `dictionary` table: 124,111 entries (nouns, verbs, Partizip II, Präteritum, adjectives).
  - `verb_forms` table: 8,005 verbs with full conjugation sets `(infinitive, praeteritum, partizip2, hilfsverb)`.
- **`data/translations_cache.db`**: Local cache of German-to-English translations (works offline without latency).
- **`~/.simple_wb_history`**: Persistent REPL command and word history (navigate with ↑ / ↓ arrows).

---

## 🧪 Running Tests

The test suite validates parsing, heuristics, separable verbs, auxiliary verbs, operator syntax, dictionary search, and database operations:
```bash
PYTHONPATH=. python3 tests/test_parser.py
```
Expected output:
```text
All 21 tests passed ✓
```
