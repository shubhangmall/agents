---
title: deep_research
app_file: deep_research.py
sdk: gradio
sdk_version: 5.44.1
---

# Deep Research Agent

A polished, full‑stack demonstration of an autonomous research assistant built and maintained by **Shubhang Mall**. This system uses a team of specialized agents to take a user query, plan a research strategy, scour the web, synthesize findings, and optionally email the final report.

## How It Works

- **Planner Agent** builds a high‑level task list based on the query.
- **Search Agent** performs web searches and returns raw snippets.
- **Writer Agent** crafts narrative summaries and assembles the final report.
- **Email Agent** (optional) can send the completed document to a specified address.
- `ResearchManager` coordinates the above and streams status updates to the UI.

The architecture showcases asynchronous workflows, streaming OpenAI responses, and clean separation of concerns between agents.

## Installation

```bash
cd deep_research
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your_key_here"
```

> You can also manage dependencies with `uv`/`crewai` if you prefer, as shown in other subprojects.

## Running the App

```bash
python deep_research.py
```

A Gradio interface will open in your browser (`http://localhost:7860`). Enter any topic, click **Run**, and watch the agent team generate a report over the next minute or so.

## Customization & Extension

- Modify `research_manager.py` to adjust orchestration logic or add new agents.
- Add additional agent modules (e.g. `analysis_agent.py`) following the existing pattern.
- Change notification settings via environment variables such as `PUSHOVER_TOKEN` to get mobile alerts when research completes.

## Why This Matters

This project is a compelling example of how to build a multi‑agent pipeline on top of the OpenAI ecosystem. It's an ideal showcase for recruiters or collaborators interested in large‑scale, real‑world AI architectures.
