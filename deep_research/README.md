---
title: deep_research
app_file: deep_research.py
sdk: gradio
sdk_version: 5.44.1
---

# Deep Research Agent

A provider-independent autonomous research assistant built and maintained by **Shubhang Mall**. It uses a configurable LLM for planning and writing, Tavily Basic for web evidence, and optional SendGrid delivery.

## How It Works

- **Planner** builds a bounded search plan through the provider-neutral LLM client.
- **Search** runs concurrent Tavily Basic queries and normalizes source metadata.
- **Writer** synthesizes the evidence and streams a Markdown report with source IDs through the same LLM client.
- **Email** (optional) can send the completed document to a specified address.
- `ResearchManager` coordinates the above and streams status updates to the UI.

The initial configuration uses OpenRouter's `openrouter/free` route and Tavily Basic. The declared planner and streaming contract for the default route is JSON-object generation plus local Pydantic validation, and OpenAI-compatible SSE streaming. Groq (`llama-3.3-70b-versatile`) and Ollama (`llama3.2`) use the same explicit contract. Other provider/model combinations are rejected until declared. `SEARCH_EVIDENCE_MAX_CHARS` bounds each search's evidence context (default 12,000 characters). Ollama running on `localhost` cannot automatically be reached from a cloud deployment.

## Installation

```bash
cd deep_research
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure the required provider variables in `.env` or the deployment environment. Deployment/shell-injected values take precedence over `.env`; never commit secrets.

## Running the App

```bash
python deep_research.py
```

A Gradio interface will open in your browser (`http://localhost:7860`). Enter any topic, click **Run**, and watch the agent team generate a report over the next minute or so.

Email delivery is disabled by default. To enable the optional SendGrid step, set `SEND_RESEARCH_EMAIL=true` and configure `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, and `SENDGRID_TO_EMAIL`. Email failures are logged server-side and do not discard a completed report.

## Customization & Extension

- Modify `research_manager.py` to adjust orchestration logic or add new agents.
- Add additional agent modules (e.g. `analysis_agent.py`) following the existing pattern.
- Adjust the LLM, Tavily, Gradio, and optional SendGrid configuration through environment variables in `.env`.

## Why This Matters

This project is an example of an asynchronous research pipeline with replaceable hosted or local LLM backends, deterministic source provenance, and optional email delivery. No public cloud hosting or provider configuration is guaranteed to be free.
