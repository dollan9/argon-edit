"""Style Memory Vector Store for Project Argon.

Stores user editing style preferences, pacing rules, and LUT choices in ChromaDB
(with a persistent fallback vector store) so the Director Agent permanently adapts.
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

from config.settings import get_settings
from agents.base_agent import BaseNvidiaAgent

logger = logging.getLogger("argon.memory.style")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class StyleMemory:
    """Manages persistent vector memory for director editing styles and rules."""

    def __init__(
        self,
        persist_dir: Optional[Path] = None,
        agent: Optional[BaseNvidiaAgent] = None,
    ):
        settings = get_settings()
        self.persist_dir = persist_dir or settings.style_memory_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.agent = agent or BaseNvidiaAgent()
        self.chroma_client = None
        self.collection = None
        self.fallback_file = self.persist_dir / "fallback_style_rules.json"

        self._init_chroma()

    def _init_chroma(self) -> None:
        """Attempt to initialize ChromaDB persistent client."""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self.chroma_client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self.collection = self.chroma_client.get_or_create_collection(
                name="argon_editing_rules"
            )
            logger.info("ChromaDB vector store initialized successfully.")
        except Exception as e:
            logger.warning(f"ChromaDB initialization failed ({e}). Using embedded JSON vector fallback.")
            self.chroma_client = None
            self.collection = None

    def _read_fallback(self) -> List[Dict[str, Any]]:
        if self.fallback_file.exists():
            try:
                with open(self.fallback_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _write_fallback(self, rules: List[Dict[str, Any]]) -> None:
        with open(self.fallback_file, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2)

    async def add_rule(
        self,
        rule_description: str,
        parameters: Optional[Dict[str, Any]] = None,
        category: str = "pacing",
    ) -> str:
        """Add an editing rule or style preference to vector memory."""
        rule_id = f"rule_{abs(hash(rule_description)) % 1000000}"
        params = parameters or {}
        param_str = json.dumps(params)

        # Get embedding if agent key is set
        embedding = None
        if self.agent.api_key:
            try:
                emb_res = await self.agent.get_embeddings([rule_description])
                if emb_res:
                    embedding = emb_res[0]
            except Exception as e:
                logger.warning(f"Embedding calculation skipped ({e}).")

        # ChromaDB path
        if self.collection is not None:
            try:
                meta = {"category": category, "parameters": param_str}
                if embedding is not None:
                    self.collection.upsert(
                        ids=[rule_id],
                        documents=[rule_description],
                        metadatas=[meta],
                        embeddings=[embedding],
                    )
                else:
                    self.collection.upsert(
                        ids=[rule_id],
                        documents=[rule_description],
                        metadatas=[meta],
                    )
                logger.info(f"Saved rule '{rule_description[:40]}...' to ChromaDB.")
                return rule_id
            except Exception as e:
                logger.warning(f"ChromaDB upsert error: {e}. Writing to fallback store.")

        # Fallback JSON path
        rules = self._read_fallback()
        # Remove existing if same ID
        rules = [r for r in rules if r.get("rule_id") != rule_id]
        rules.append({
            "rule_id": rule_id,
            "description": rule_description,
            "category": category,
            "parameters": params,
            "embedding": embedding,
        })
        self._write_fallback(rules)
        logger.info(f"Saved rule '{rule_description[:40]}...' to fallback store.")
        return rule_id

    async def query_rules(self, query_text: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Query matching editing style rules."""
        # 1. ChromaDB query
        if self.collection is not None:
            try:
                results = self.collection.query(
                    query_texts=[query_text],
                    n_results=top_k,
                )
                rules = []
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                ids = results.get("ids", [[]])[0]
                for i in range(len(docs)):
                    meta = metas[i] if i < len(metas) else {}
                    p = meta.get("parameters", "{}")
                    try:
                        p_dict = json.loads(p) if isinstance(p, str) else p
                    except Exception:
                        p_dict = {}
                    rules.append({
                        "rule_id": ids[i] if i < len(ids) else f"id_{i}",
                        "description": docs[i],
                        "category": meta.get("category", "general"),
                        "parameters": p_dict,
                    })
                return rules
            except Exception as e:
                logger.warning(f"ChromaDB query error: {e}. Querying fallback store.")

        # 2. Fallback JSON query
        all_rules = self._read_fallback()
        if not all_rules:
            return []

        query_emb = None
        if self.agent.api_key:
            try:
                embs = await self.agent.get_embeddings([query_text])
                if embs:
                    query_emb = np.array(embs[0])
            except Exception:
                pass

        if query_emb is not None:
            scored = []
            for r in all_rules:
                if r.get("embedding"):
                    r_vec = np.array(r["embedding"])
                    score = float(np.dot(query_emb, r_vec) / (np.linalg.norm(query_emb) * np.linalg.norm(r_vec) + 1e-9))
                else:
                    # Token overlap score
                    q_words = set(query_text.lower().split())
                    d_words = set(r["description"].lower().split())
                    score = len(q_words & d_words) / (len(q_words | d_words) + 1e-5)
                scored.append((score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [x[1] for x in scored[:top_k]]

        # Keyword matching fallback
        q_words = set(query_text.lower().split())
        scored = []
        for r in all_rules:
            d_words = set(r["description"].lower().split())
            score = len(q_words & d_words)
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:top_k]]
