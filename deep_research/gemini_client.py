import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

MODEL = "gemini-2.5-flash"
_client: genai.Client | None = None


def _api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return api_key


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=_api_key())
    return _client


async def generate_content(contents: str, *, config: types.GenerateContentConfig | dict | None = None):
    return await _get_client().aio.models.generate_content(
        model=MODEL,
        contents=contents,
        config=config,
    )


async def stream_content(contents: str, *, config: types.GenerateContentConfig | dict | None = None) -> AsyncIterator[str]:
    stream = await _get_client().aio.models.generate_content_stream(
        model=MODEL,
        contents=contents,
        config=config,
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
