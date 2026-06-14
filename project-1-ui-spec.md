# Project 1: UI Spec — Terminal Spotlight

## Concept

A single-page browser UI that combines a terminal aesthetic with command palette interaction. Dark background, monospace font throughout, light green answer text. Two modes in one input: instant search results as you type (FTS/semantic), and a full AI-generated answer when explicitly requested.

---

## Visual Design

### Colors

| Element | Value |
|---|---|
| Page background | `#0d0d0d` |
| Input row background | `#111` |
| Answer block background | `#0a1a0a` |
| Active result background | `#161616` |
| Default border | `#2a2a2a` |
| Answer block border | `#1a2e1a` |
| Active result border (accent) | `#c8ffc822` |
| **Answer text** | **`#c8ffc8`** (pale green) |
| Result titles | `#d0d0d0` |
| Snippets / secondary text | `#555` |
| Highlighted match in snippet | `#c8ffc8` |
| Timestamps / meta | `#3a3a3a` |
| Status indicator (online) | `#1db954` |
| Footer keyboard hints | `#333` |
| Prompt character `›` | `#555` |
| Caret color | `#c8ffc8` |

### Typography

- Font: monospace throughout — use `var(--font-mono)` or fallback `'Courier New', monospace`
- No serif, no sans-serif anywhere in the UI
- Font sizes:
  - Top bar labels: 10px
  - Search input: 13px
  - Answer text: 12px
  - Result title: 12px
  - Result snippet: 11px
  - Source tags: 9px uppercase
  - Footer hints: 10px
  - Timestamps: 10px

### Source tag colors

Each data source gets a distinct pill color. Background is a dark tint, text is a lighter version of the same hue.

| Source | Background | Text |
|---|---|---|
| keep | `#1a2a1a` | `#4ade80` |
| twitter | `#1a1f2e` | `#60a5fa` |
| bookmark | `#2a1f1a` | `#fb923c` |
| pdf | `#261a2a` | `#c084fc` |
| markdown | `#1a2020` | `#2dd4bf` |
| notion | `#1e1a2a` | `#a78bfa` |

Add new source types here as ingest scripts are added. Pattern: dark tinted bg + lighter matching text.

---

## Layout

Single page, no navigation, no sidebar. Full viewport height. Three vertical zones:

```
┌─────────────────────────────────┐
│  top bar (status line)          │  ~32px
├─────────────────────────────────┤
│  search input row               │  ~40px
├─────────────────────────────────┤
│                                 │
│  results area (scrollable)      │  flex: 1
│  ├── answer block (if AI query) │
│  ├── divider                    │
│  └── result items               │
│                                 │
├─────────────────────────────────┤
│  footer (keyboard hints)        │  ~32px
└─────────────────────────────────┘
```

Outer padding: `24px 20px`. No max-width constraint — fills the browser tab naturally.

---

## Components

### Top bar

```
PERSONAL KB                    ● 1,842 memories · llama3.2:3b
```

- Left: `PERSONAL KB` in 10px, `#555`, letter-spacing `0.08em`
- Right: green dot + count + model name in 10px, `#1db954`
- Green dot: 5px circle, same green as status text
- Count updates from `/status` API on page load
- If Ollama is not running: dot turns `#ff4444`, text shows `ollama offline`

### Search input row

```
› [                                          ] ⌘K
```

- Full-width row with 1px `#2a2a2a` border, `#111` background, 6px border-radius
- `›` prompt character on the left, `#555`
- Text input fills remaining space — transparent background, `#f0f0f0` text, `#c8ffc8` caret
- `⌘K` shortcut hint on the right, `#444`
- Input is autofocused on page load
- `⌘K` (or `Ctrl+K`) anywhere on the page refocuses the input

### Results area

Scrollable. Contains up to three things in order:

1. **Answer block** — only visible after a `⌘↵` query, hidden on initial load
2. **Divider** — 1px `#1a1a1a` horizontal rule, only shown when answer block is visible
3. **Result items** — shown as user types (live search), empty state when input is blank

#### Answer block

```
▸ ANSWER
[answer text in #c8ffc8]

[keep] [bookmark] [twitter]
```

- Background: `#0a1a0a`, border: 1px `#1a2e1a`, border-radius: 6px, padding: 12px
- `▸ ANSWER` label: 9px, `#4ade80`, letter-spacing `0.1em`
- Answer text: 12px, `#c8ffc8`, line-height 1.7
- Source tags rendered as pills below the answer text
- Appears with a fade-in when the AI response arrives (CSS `opacity` transition, 150ms)
- Shows a blinking cursor `▋` at end of text while streaming, removed when done

#### Result item

```
[source-tag] result title
snippet text with highlighted match
timestamp
```

- Padding: `9px 12px`, border-radius: 5px
- Default: transparent background, transparent border
- Hover / active: `#161616` background, 1px `#2a2a2a` border
- Active item additionally gets 1px `#c8ffc822` border (subtle green tint)
- Title: 12px, `#d0d0d0`
- Snippet: 11px, `#555` — matched terms highlighted in `#c8ffc8`, wrapped in `<em>` (non-italic)
- Timestamp: 10px, `#3a3a3a`, human-readable relative time ("2 months ago", "Apr 2024")

#### Empty state (no query)

When the input is blank, show:

```
› start typing to search your notes
  or press ⌘↵ to ask a question
```

Both lines in `#333`, 11px, centered vertically in the results area.

#### Loading state (AI query in progress)

Replace answer block content with:

```
▸ ANSWER
thinking▋
```

`thinking` in `#555`, blinking cursor in `#c8ffc8`.

#### No results state

```
no matches for "xyz"
```

11px, `#444`, left-aligned, 12px padding.

### Footer

```
↑↓ navigate    ↵ open source    ⌘↵ ask AI    esc clear
```

- Fixed to bottom of the page
- 1px `#1a1a1a` top border
- All text: 10px, `#333`
- `kbd` elements: 9px, `#555`, `#1a1a1a` background, 1px `#2a2a2a` border, 3px border-radius

---

## Interactions

### Typing in the search box

- Debounce: 200ms after last keystroke
- Fires `GET /search?q={query}&limit=8`
- Results render immediately below, replacing previous results
- No answer block shown (answer block only appears on explicit AI query)

### Keyboard navigation

| Key | Action |
|---|---|
| `↑` / `↓` | Move active highlight between result items |
| `↵` | Open the active result's source (Keep note, tweet, bookmark URL, etc.) in a new tab |
| `⌘↵` / `Ctrl+↵` | Fire AI query — POST to `/query`, show answer block |
| `Esc` | Clear input, hide answer block, return to empty state |
| `⌘K` / `Ctrl+K` | Focus search input from anywhere on the page |

### Mouse

- Hover over result item → sets it as active (same style as keyboard active)
- Click result item → same as `↵` (opens source)

### Answer streaming

- `/query` endpoint should support streaming (`stream: true` in Ollama API call)
- Answer text renders token by token into the answer block
- Blinking cursor `▋` appended during stream, removed on completion
- Source tags appear after streaming completes

---

## API calls this UI makes

| Action | Endpoint | When |
|---|---|---|
| Page load | `GET /status` | Populate top bar count + model name |
| Typing | `GET /search?q=&limit=8` | Debounced 200ms |
| AI query | `POST /query` `{question: str}` | `⌘↵` |

Responses expected:

```json
// GET /status
{ "documents_indexed": 1842, "ollama_running": true, "model": "llama3.2:3b" }

// GET /search
[
  {
    "id": 1,
    "source": "keep",
    "title": "10pm phone off note",
    "snippet": "10pm phone off, no caffeine after 2",
    "timestamp": "2 months ago",
    "url": null
  }
]

// POST /query → streamed plain text, sources in final JSON chunk
```

---

## File structure

```
ui/
├── index.html      — full page shell, mounts all three zones
├── style.css       — all colors and layout as CSS variables/classes
└── app.js          — search debounce, keyboard nav, API calls, streaming
```

Keep all colors as CSS custom properties at the top of `style.css` so they're easy to tweak:

```css
:root {
  --bg: #0d0d0d;
  --bg-input: #111;
  --bg-answer: #0a1a0a;
  --bg-result-active: #161616;
  --border: #2a2a2a;
  --border-answer: #1a2e1a;
  --text-answer: #c8ffc8;
  --text-title: #d0d0d0;
  --text-snippet: #555;
  --text-meta: #3a3a3a;
  --text-match: #c8ffc8;
  --accent-online: #1db954;
  --accent-offline: #ff4444;
  --prompt-char: #555;
  --caret: #c8ffc8;
}
```

---

## What NOT to build

- No settings page
- No login or auth
- No dark/light mode toggle (it's always dark)
- No mobile responsiveness (this is a local desktop tool)
- No markdown rendering in answers (plain text only, preserves the terminal feel)
- No animations beyond the answer fade-in and streaming cursor
