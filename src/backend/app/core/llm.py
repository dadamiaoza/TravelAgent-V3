"""Shared MiniMax ChatOpenAI factory.

Default model is MiniMax-M3 (OpenAI-compatible). All LLM call sites must go
through `chat_model()` so HTTP transport stays consistent.

openai>=3 talks HTTP via httpx2. MiniMax (and some CDNs) often respond with
Content-Encoding: br. httpx2's BrotliDecoder calls
brotli.Decompressor.process(..., output_buffer_limit=), but brotli 1.0.9
only accepts positional bytes. That TypeError is wrapped as
openai.APIConnectionError and surfaces as HTTP 500 on /trips/suggest.

Request gzip/deflate only so the brotli decoder is never used.

Do not set extra_body.reasoning_split here: MiniMax-M3 can put thinking into
reasoning_details, but LangChain tool loops would drop that field on the next
turn. Keep native `<think>` in content and strip it at JSON parse sites.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI
from openai import DefaultAsyncHttpxClient, DefaultHttpxClient

from app.core.config import settings

_NO_BROTLI_HEADERS = {"Accept-Encoding": "gzip, deflate"}


@lru_cache(maxsize=1)
def _sync_http_client():
    return DefaultHttpxClient(headers=_NO_BROTLI_HEADERS)


@lru_cache(maxsize=1)
def _async_http_client():
    return DefaultAsyncHttpxClient(headers=_NO_BROTLI_HEADERS)


def chat_model(**kwargs) -> ChatOpenAI:
    kwargs.setdefault("base_url", settings.llm_base_url)
    kwargs.setdefault("api_key", settings.llm_api_key)
    kwargs.setdefault("model", settings.llm_model)
    kwargs.setdefault("http_client", _sync_http_client())
    kwargs.setdefault("http_async_client", _async_http_client())
    return ChatOpenAI(**kwargs)
