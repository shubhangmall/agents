---
title: career_chatbot
app_file: app.py
sdk: gradio
sdk_version: 5.34.2
---

# Career Chatbot

An interactive, retrieval‑augmented chatbot that answers questions about the author's professional background, skills, and experience. Implemented by **Shubhang Mall**, the bot uses a résumé PDF and a summary text file as its knowledge base and showcases advanced RAG techniques with Chroma and OpenAI embeddings.

## Key Features

- **Résumé ingestion**: Automatically parses and chunks the `me/resume.pdf` file by section and role.
- **Vector store retrieval**: Stores chunks in a Chroma database with OpenAI embeddings for fast, context-aware answers.
- **Custom tools**: Includes functions to record user contact details or log unanswerable questions.
- **Gradio interface**: Simple web UI for conversational interaction or embedding into other frontends.

## Setup

```bash
cd career_chatbot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your_key_here"
```

## Running

```bash
python app.py
```

The chat interface will open automatically. Feel free to ask anything about education, projects, roles, technologies, etc. The system will build or refresh its vector index when the resume or summary changes.

## Customization

- Replace the contents of `me/resume.pdf` / `me/summary.txt` to personalize the bot for a different user.
- Adjust chunking logic in `app.py` or modify the `Me` class to add new context sources (blog posts, GitHub README, etc.).
- Add tools by updating the `tools` list and corresponding JSON schemas.

## Why It’s Impressive

This repo demonstrates full‑lifecycle RAG engineering, from PDF parsing to vector indexing to interactive deployment. It’s a clean, polished showcase for recruiting or portfolio purposes.
