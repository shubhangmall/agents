import hashlib
import json
import os
import re

import chromadb
import gradio as gr
import requests
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

load_dotenv(override=True)

# RAG config
CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chroma")
INDEX_META_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".chroma_index_meta.json"
)
COLLECTION_NAME = "career_context"
# Local ONNX MiniLM — no API key / quota (same model as Chroma's default EF)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# Gemini free-tier chat via OpenAI-compatible endpoint (keeps tool-calling loop)
CHAT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
TOP_K = 3
SUMMARY_CHUNK_ID = "summary"
MIN_CHUNKS_FOR_RAG = 1
CHUNKING_VERSION = "v2_role_level_2026-02-12"

RAG_DEBUG = os.getenv("RAG_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")

# Resume section headers commonly found in extracted text
RESUME_SECTION_HEADERS = re.compile(
    r"^(?:"
    + "|".join(
        [
            r"EXPERIENCE",
            r"TECHNICAL\s+SKILLS",
            r"SKILLS",
            r"EDUCATION",
            r"PROJECTS",
            r"CERTIFICATIONS",
            r"LANGUAGES",
            r"INTERESTS",
            r"SUMMARY",
        ]
    )
    + r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:40]


def _split_sections(text: str):
    """Return list of (section_name, section_text) including header line."""
    if not text or not text.strip():
        return []
    matches = list(RESUME_SECTION_HEADERS.finditer(text))
    if not matches:
        return [("FULL", text.strip())]
    out = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        out.append((m.group(0).strip(), section_text))
    return out


def _split_experience_roles(experience_section_text: str):
    """
    Split an EXPERIENCE section into role/company chunks.

    Heuristic: start a new chunk when a line looks like a company/location line,
    e.g. contains a '|' separator (common in your extracted resume).
    """
    lines = [ln.rstrip() for ln in (experience_section_text or "").splitlines()]
    chunks = []
    cur = []

    def flush():
        nonlocal cur
        if cur:
            chunks.append("\n".join(cur).strip())
            cur = []

    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if cur and (cur[-1].strip() != ""):
                cur.append("")
            continue
        is_company_line = ("|" in stripped) and not stripped.startswith("•")
        if is_company_line and cur:
            flush()
        cur.append(stripped)
    flush()

    # If the heuristic didn't split, return the whole section (minus header) as one chunk
    return [c for c in chunks if c]


def chunk_resume(resume_text):
    """Role-level chunking. Returns list of (id, text, metadata)."""
    chunks = []
    for section_name, section_text in _split_sections(resume_text):
        normalized = section_name.upper()
        if normalized == "EXPERIENCE":
            role_chunks = _split_experience_roles(section_text)
            for i, rc in enumerate(role_chunks):
                # Try to extract company and role from the first couple lines
                lines = [ln for ln in rc.splitlines() if ln.strip()]
                company = lines[0].split("|", 1)[0].strip() if lines else ""
                role = lines[1].strip() if len(lines) > 1 and not lines[1].startswith("•") else ""
                cid = f"exp_{i}_{_slug(company) or 'unknown'}"
                chunks.append(
                    (
                        cid,
                        rc,
                        {
                            "source": "resume",
                            "section": "Experience",
                            "company": company,
                            "role": role,
                        },
                    )
                )
        elif normalized in ("TECHNICAL SKILLS", "SKILLS"):
            cid = f"skills_{_slug(normalized)}"
            chunks.append((cid, section_text, {"source": "resume", "section": "Skills"}))
        elif normalized == "EDUCATION":
            chunks.append(("education", section_text, {"source": "resume", "section": "Education"}))
        else:
            # Keep other sections as single chunks (projects/certs/etc.)
            cid = f"sec_{_slug(normalized)}"
            chunks.append((cid, section_text, {"source": "resume", "section": normalized.title()}))
    return [c for c in chunks if c[1] and c[1].strip()]


def compute_index_fingerprint(resume_pdf_path: str, summary_txt_path: str):
    """Fingerprint used to decide whether to rebuild the vector index."""

    def stat_sig(p: str):
        st = os.stat(p)
        return {"path": os.path.basename(p), "mtime": int(st.st_mtime), "size": int(st.st_size)}

    payload = {
        "chunking_version": CHUNKING_VERSION,
        "resume": stat_sig(resume_pdf_path),
        "summary": stat_sig(summary_txt_path),
        "embedding_model": EMBEDDING_MODEL,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), payload


def push(text):
    requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": os.getenv("PUSHOVER_TOKEN"),
            "user": os.getenv("PUSHOVER_USER"),
            "message": text,
        },
    )


def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"Recording {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}


def record_unknown_question(question):
    push(f"Recording {question}")
    return {"recorded": "ok"}


record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "The email address of this user"},
            "name": {"type": "string", "description": "The user's name, if they provided it"},
            "notes": {
                "type": "string",
                "description": "Any additional information about the conversation that's worth recording to give context",
            },
        },
        "required": ["email"],
        "additionalProperties": False,
    },
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question that couldn't be answered"},
        },
        "required": ["question"],
        "additionalProperties": False,
    },
}

tools = [
    {"type": "function", "function": record_user_details_json},
    {"type": "function", "function": record_unknown_question_json},
]


class Me:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GOOGLE_API_KEY for Gemini chat (free tier)")
        self.openai = OpenAI(api_key=api_key, base_url=GEMINI_OPENAI_BASE)
        self.name = "Shubhang Mall"
        self._resume_pdf_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "me", "resume.pdf"
        )
        self._summary_txt_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "me", "summary.txt"
        )

        reader = PdfReader(self._resume_pdf_path)
        self.resume_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                self.resume_text += text
        with open(self._summary_txt_path, encoding="utf-8") as f:
            self.summary = f.read()

        # RAG: persistent Chroma + local embeddings (startup must not hit OpenAI)
        os.makedirs(CHROMA_PATH, exist_ok=True)
        self._chroma = chromadb.PersistentClient(path=CHROMA_PATH)
        self._ef = embedding_functions.ONNXMiniLM_L6_V2()
        self._collection = self._chroma.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"description": "Career context for RAG"},
        )
        self._ensure_fresh_index()

    def _ensure_fresh_index(self):
        """Auto-rebuild the index when resume/summary or chunking logic changes."""
        fingerprint, payload = compute_index_fingerprint(
            self._resume_pdf_path, self._summary_txt_path
        )
        existing = None
        try:
            if os.path.exists(INDEX_META_PATH):
                with open(INDEX_META_PATH, encoding="utf-8") as f:
                    existing = json.load(f)
        except Exception:
            existing = None

        if existing and existing.get("fingerprint") == fingerprint and self._collection.count() > 0:
            return

        # Rebuild
        try:
            self._chroma.delete_collection(name=COLLECTION_NAME)
        except Exception:
            pass
        self._collection = self._chroma.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"description": "Career context for RAG"},
        )
        self._build_index()
        try:
            with open(INDEX_META_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {"fingerprint": fingerprint, "details": payload}, f, indent=2, sort_keys=True
                )
        except Exception:
            pass

    def _build_index(self):
        """Chunk resume and summary, embed and store in Chroma."""
        ids, documents, metadatas = [], [], []
        # Summary as one chunk (always included in retrieval)
        if self.summary.strip():
            ids.append(SUMMARY_CHUNK_ID)
            documents.append(self.summary.strip())
            metadatas.append({"source": "summary"})
        for cid, text, meta in chunk_resume(self.resume_text):
            ids.append(cid)
            documents.append(text)
            metadatas.append(meta)
        if documents:
            self._collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def retrieve(self, query):
        """Return context string from RAG (top-k chunks + summary). Fallback to full text if needed."""
        try:
            # Query more than TOP_K so we can apply section-aware selection.
            results = self._collection.query(
                query_texts=[query],
                n_results=min(TOP_K + 5, self._collection.count()),  # get enough to filter
                include=["documents", "metadatas", "distances"],
            )
            docs = results["documents"][0] if results["documents"] else []
            metas = results["metadatas"][0] if results["metadatas"] else []
            ids = results["ids"][0] if results.get("ids") else []
            if not docs or len(docs) < MIN_CHUNKS_FOR_RAG:
                return self._fallback_context()

            q = (query or "").lower()
            wants_education = any(k in q for k in ("education", "school", "university", "degree"))
            wants_skills = any(
                k in q for k in ("skill", "stack", "technology", "tools", "framework", "language")
            )

            # Build unique chunks: always include summary, then pick up to TOP_K relevant chunks with light diversity
            summary_text = None
            candidates = []
            for doc, meta, cid in zip(docs, metas, ids):
                if meta and meta.get("source") == "summary":
                    summary_text = doc
                else:
                    candidates.append((cid, doc, meta or {}))
            if summary_text is None and self._collection.count() > 0:
                try:
                    got = self._collection.get(ids=[SUMMARY_CHUNK_ID], include=["documents"])
                    if got["documents"]:
                        summary_text = got["documents"][0]
                except Exception:
                    pass

            # Re-rank: prioritize education/skills sections when the query clearly asks for them.
            def score(meta: dict):
                sec = (meta.get("section") or "").lower()
                s = 0
                if wants_education and "education" in sec:
                    s += 10
                if wants_skills and "skills" in sec:
                    s += 10
                return s

            candidates_sorted = sorted(candidates, key=lambda t: score(t[2]), reverse=True)

            selected = []
            seen_text = set()
            experience_taken = 0
            for cid, doc, meta in candidates_sorted:
                if doc in seen_text:
                    continue
                sec = (meta.get("section") or "").lower()
                is_experience = "experience" in sec
                # diversity: prefer at most one Experience chunk unless the query is company-specific
                if (
                    is_experience
                    and experience_taken >= 1
                    and not any(
                        (meta.get("company") or "").lower() in q for _, _, meta in candidates_sorted
                    )
                ):
                    continue
                selected.append((cid, doc, meta))
                seen_text.add(doc)
                if is_experience:
                    experience_taken += 1
                if len(selected) >= TOP_K:
                    break

            parts = []
            if summary_text:
                parts.append(f"## Summary:\n{summary_text}")
            if selected:
                parts.append("## Resume (excerpts):\n" + "\n\n".join([d for _, d, _ in selected]))
            if RAG_DEBUG:
                dbg = [
                    {
                        "id": cid,
                        "section": meta.get("section"),
                        "company": meta.get("company"),
                        "role": meta.get("role"),
                    }
                    for cid, _, meta in selected
                ]
                print("[RAG_DEBUG] selected_chunks:", json.dumps(dbg, ensure_ascii=False))
            return "\n\n".join(parts) if parts else self._fallback_context()
        except Exception:
            return self._fallback_context()

    def _fallback_context(self):
        """Full summary + resume when RAG returns too little."""
        return f"## Summary:\n{self.summary}\n\n## Resume:\n{self.resume_text}"

    def handle_tool_call(self, tool_calls):
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(f"Tool called: {tool_name}", flush=True)
            tool = globals().get(tool_name)
            result = tool(**arguments) if tool else {}
            results.append(
                {"role": "tool", "content": json.dumps(result), "tool_call_id": tool_call.id}
            )
        return results

    def system_prompt(self, context):
        system_prompt = f"You are acting as {self.name}. You are answering questions on {self.name}'s website, \
particularly questions related to {self.name}'s career, background, skills and experience. \
Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible. \
You are given a summary of {self.name}'s background and resume which you can use to answer questions. \
Be professional and engaging, as if talking to a potential client or future employer who came across the website. \
If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. \
If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool. "

        system_prompt += f"\n\n{context}\n\n"
        system_prompt += f"With this context, please chat with the user, always staying in character as {self.name}."
        return system_prompt

    def chat(self, message, history):
        context = self.retrieve(message)
        if RAG_DEBUG:
            print("\nQUESTION:", message)
            print("CONTEXT LENGTH:", len(context))
            print(context[:300].replace("\n", " "))
        messages = (
            [{"role": "system", "content": self.system_prompt(context)}]
            + history
            + [{"role": "user", "content": message}]
        )
        done = False
        while not done:
            response = self.openai.chat.completions.create(
                model=CHAT_MODEL, messages=messages, tools=tools
            )
            if response.choices[0].finish_reason == "tool_calls":
                message = response.choices[0].message
                tool_calls = message.tool_calls
                results = self.handle_tool_call(tool_calls)
                messages.append(message)
                messages.extend(results)
            else:
                done = True
        return response.choices[0].message.content


if __name__ == "__main__":
    me = Me()
    gr.ChatInterface(me.chat, type="messages").launch()
