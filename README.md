# hn-lens

A terminal-based Hacker News reader with built-in LLM-powered translation. Read HN, learn English.

## Features

- **Real-time HN feeds**: Top stories and Ask HN via Algolia public API (works in China)
- **LLM Translation**: Select any story or comment, press `T` to translate via DeepSeek/OpenAI-compatible API
- **Translation cache**: Results cached locally to save API tokens
- **CJK-aware rendering**: Proper line wrapping for Chinese/English mixed content
- **Tree-style comments**: Visual indentation guides for comment threads
- **Keyboard-driven**: Full navigation without mouse
- **Safe exit**: Ctrl+C triggers confirmation before quitting

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and edit config
cp config.example.json ~/.hn/config.json
vim ~/.hn/config.json  # Set your API key

# Run
python hn
```

## Keybindings

| Key | Action |
|-----|--------|
| `j` / `k` | Navigate down / up |
| `g` / `G` | Go to top / bottom |
| `o` / `Enter` | Open story detail |
| `c` | View comments |
| `a` | Read article in terminal |
| `u` | Open URL in browser |
| `/` | Search stories |
| `T` | Translate selected item |
| `r` | Refresh feed |
| `1` / `2` | Switch feed (Top / Ask) |
| `q` | Quit |

### Translation Popup

| Key | Action |
|-----|--------|
| `j` / `k` | Scroll results |
| `PageUp` / `PageDown` | Fast scroll |
| `Esc` | Close |

## Configuration

Edit `~/.hn/config.json`:

```json
{
  "api_url": "https://api.deepseek.com/v1/chat/completions",
  "api_key": "sk-your-key-here",
  "api_model": "deepseek-chat"
}
```

Supports any OpenAI-compatible API (DeepSeek, OpenAI, Ollama, etc.).

## Requirements

- Python 3.10+
- `requests` library
- A terminal with 256-color support

## License

MIT
