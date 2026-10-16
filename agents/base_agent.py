"""Base Nvidia NIM API Client for Argon Video Engine Agents.

Provides robust, rate-limited, asynchronous completions pointed at
https://integrate.api.nvidia.com/v1 using httpx with automatic retries,
model fallbacks, and strict JSON parsing.
"""

from __future__ import annotations
import os
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx
from config.settings import get_settings

logger = logging.getLogger("argon.agents.base")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class BaseNvidiaAgent:
    """Async client communicating with Nvidia NIM OpenAI-compatible API endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        timeout: float = 90.0,
        max_retries: int = 3,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.nvidia_api_key or os.getenv("NVIDIA_API_KEY", "")
        self.base_url = (base_url or settings.nvidia_base_url).rstrip("/")
        self.default_model = default_model or settings.director_model
        self.fallback_model = fallback_model or settings.director_fallback_model
        self.timeout = timeout
        self.max_retries = max_retries

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, str]] = None,
    ) -> str:
        """Execute chat completion with retry and fallback logic."""
        target_model = model or self.default_model
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            attempt = 0
            while attempt < self.max_retries:
                attempt += 1
                try:
                    logger.info(
                        f"Sending completion request to Nvidia NIM (model={target_model}, attempt={attempt}/{self.max_retries})"
                    )
                    resp = await client.post(url, headers=headers, json=payload)

                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if not choices:
                            raise ValueError(f"No choices in Nvidia NIM response: {data}")
                        return choices[0]["message"]["content"]

                    if resp.status_code in (429, 500, 502, 503, 504):
                        wait_sec = (2 ** attempt) + 1.0
                        logger.warning(
                            f"Nvidia NIM API returned HTTP {resp.status_code}: {resp.text[:200]}. Retrying in {wait_sec:.1f}s..."
                        )
                        await asyncio.sleep(wait_sec)
                        continue

                    # If model not found or forbidden, try fallback model if available
                    if resp.status_code in (404, 400) and self.fallback_model and target_model != self.fallback_model:
                        logger.warning(
                            f"Primary model {target_model} failed (HTTP {resp.status_code}). Falling back to {self.fallback_model}."
                        )
                        target_model = self.fallback_model
                        payload["model"] = target_model
                        continue

                    resp.raise_for_status()

                except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                    logger.warning(f"Network error on attempt {attempt}: {net_err}")
                    if attempt < self.max_retries:
                        await asyncio.sleep((2 ** attempt) + 0.5)
                    else:
                        raise

            raise RuntimeError(f"Nvidia NIM API request failed after {self.max_retries} attempts.")

    async def chat_completion_json(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Request JSON formatted output and return parsed python dictionary."""
        # Enforce json instruction in system prompt if not present
        has_json_instruction = any("json" in str(m.get("content", "")).lower() for m in messages)
        if not has_json_instruction:
            messages = [
                {"role": "system", "content": "You are a precise data engine. You must output ONLY valid, parseable JSON."}
            ] + messages

        raw_text = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )

        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as jde:
            logger.error(f"Failed to decode JSON from NIM response: {jde}\nRaw content:\n{raw_text}")
            raise ValueError(f"Invalid JSON returned by model: {jde}") from jde

    async def get_embeddings(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """Compute text embeddings using Nvidia NIM nv-embedqa-e5-v5."""
        settings = get_settings()
        target_model = model or settings.embedding_model
        url = f"{self.base_url}/embeddings"
        headers = self._get_headers()

        payload = {
            "model": target_model,
            "input": texts,
            "input_type": "passage",
            "encoding_format": "float"
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]
