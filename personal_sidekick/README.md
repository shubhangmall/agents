# Sidekick Personal Co-Worker

A personal AI assistant built as a Gradio application. Sidekick maintains conversation history, long‑term memory, and can execute custom tools defined in `sidekick_tools.py`. Developed by **Shubhang Mall** as a demonstration of agent workflows with persistent state.

## Quick Start

```bash
cd personal_sidekick
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Playwright tools may require additional install:
#   playwright install
export OPENAI_API_KEY="your_key_here"
```

## Running

```bash
python app.py
```

A Gradio chat interface will open in your browser. Enter your message and (optionally) success criteria, and Sidekick will respond, updating its memory in `memory.db`.

## Project Structure

- `sidekick.py` – core logic managing supersteps, tools, and memory interactions.
- `sidekick_tools.py` – example utility functions (web search, clipboard, etc.) accessible to the agent.
- `memory.db` – SQLite file storing conversation history and knowledge for persistent context.
- `app.py` – Gradio front‑end connecting to Sidekick logic.

## Extending

Add new tools by editing `sidekick_tools.py` and registering them in the `Sidekick` class. Customize memory behaviour, success criteria, or UI elements as needed.

This project highlights the ability to build a conversational agent that is both interactive and stateful — a valuable skill for building personal assistants or team bots.
