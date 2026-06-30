# Multi-Agent AI Projects by Shubhang Mall

Welcome to the **agents** repository—a showcase of advanced, production‑grade AI agents and orchestration systems built by **Shubhang Mall**. Each sub‑directory contains a self‑contained project demonstrating expertise in:

- autonomous multi‑agent coordination
- retrieval‑augmented generation (RAG)
- custom tooling and environments
- rapid prototyping with Gradio, CrewAI, OpenAI APIs, and more

## Repository Structure

- `agent_creating_agent/` – experimental framework where agents generate and improve other agents. Includes 20+ sample agents and a `world.py` orchestrator.
- `deep_research/` – an end‑to‑end research assistant that plans, searches the web, writes reports, and even emails results.
- `pr_agent/` – PR merge-readiness agent that triages CI failures and review comments, proposes scoped fixes, and optionally posts a summary comment.
- `career_chatbot/` – interactive career advice bot with résumé RAG and personalized context.
- `personal_sidekick/` – personal co‑worker with long‑term memory and tool integration.
- `engineering_team/`, `financial_researcher/`, `stock_picker/` – crewAI‑based multi‑agent crews solving engineering tasks, financial analysis, and stock recommendations.
- More experiments and supporting material in other folders.

> 🔗 Each project includes its own `README.md` with usage instructions. Jump straight to it when you want to run or inspect a specific agent.

## Core Technologies

- **Python 3.10+** – primary language
- **OpenAI API / Models** – GPT‑4o‑mini, etc.
- **Gradio** – interactive front‑ends
- **crewAI** – agent orchestration framework for crew projects
- **Chromadb** – vector store for RAG
- **dotenv, requests, pypdf, playwright, etc.** – supporting libraries for IO, scraping, automation
- **Custom tooling** – sidekick_tools, world builders, and more

## Getting Started

```bash
git clone git@github.com:<your‑username>/agents.git
cd agents
# set OPENAI_API_KEY (and PUSHOVER for notifications, if used)
export OPENAI_API_KEY=...
# navigate into any sub‑project and follow its README
cd deep_research
python deep_research.py   # example
```

## Why This Repository Matters

Shubhang constructs complex agent ecosystems that demonstrate:

- **Modularity:** Each agent has a clear responsibility and communicates via defined protocols.
- **Scalability:** Many projects use asynchronous workers, vector stores, and queueing to scale workflows.
- **Innovation:** Experiments like `agent_creating_agent` show creative uses of agents to bootstrap others.
- **Practical Impact:** Tools like the career chatbot or engineering crew could be deployed as real products.

Whether you're a recruiter, collaborator, or curious developer, this repo illustrates Shubhang’s technical vision and ability to architect intelligent systems end‑to‑end.

---

> ✨ **Tip:** Start with `deep_research` or `career_chatbot` to quickly interact with a live UI; the crew projects are great for exploring multi‑agent orchestration.
