"""
rag_memory.py
─────────────
RAG-Based Memory module for Birthday Wishes Agent.

Uses ChromaDB (vector database) to store and retrieve
contact memories with semantic search capability.

Unlike the basic memory.py (which uses exact SQLite lookups),
RAG memory can:
  - Find semantically similar past conversations
  - Retrieve relevant context even with different wording
  - Build richer, more nuanced wish prompts
  - Store unlimited memory per contact

Architecture:
  - ChromaDB: Local vector store (no external API needed)
  - Sentence Transformers: Text → embeddings
  - LangChain: RAG pipeline for wish generation

Collections:
  - contact_memories : One document per contact per year
  - conversation_logs: Full conversation history
  - profile_snapshots: LinkedIn profile snapshots over time

Setup:
    pip install chromadb sentence-transformers langchain-chroma

Usage:
    from rag_memory import (
        init_rag_memory,
        save_memory_to_rag,
        retrieve_relevant_memory,
        generate_rag_wish
    )
"""

import logging
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CHROMA_DIR = Path("chroma_db")


# ──────────────────────────────────────────────
# INIT
# ──────────────────────────────────────────────
def init_rag_memory():
    """
    Initialize ChromaDB collections for contact memory.
    Creates the local vector store if it doesn't exist.
    """
    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

        # Create collections if they don't exist
        client.get_or_create_collection(
            name="contact_memories",
            metadata={"hnsw:space": "cosine"},
        )
        client.get_or_create_collection(
            name="conversation_logs",
            metadata={"hnsw:space": "cosine"},
        )
        client.get_or_create_collection(
            name="profile_snapshots",
            metadata={"hnsw:space": "cosine"},
        )

        logger.info("🧠 RAG Memory initialized at: %s", CHROMA_DIR)
        return client

    except ImportError:
        logger.error(
            "❌ ChromaDB not installed. Run: pip install chromadb sentence-transformers"
        )
        return None
    except Exception as e:
        logger.error("❌ RAG Memory init failed: %s", e)
        return None


def _get_client():
    """Get or create ChromaDB client."""
    try:
        import chromadb
        from chromadb.config import Settings
        return chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
    except Exception as e:
        logger.error("❌ Could not connect to ChromaDB: %s", e)
        return None


# ──────────────────────────────────────────────
# SAVE MEMORY
# ──────────────────────────────────────────────
def save_memory_to_rag(
    contact: str,
    memory_text: str,
    memory_type: str = "general",
    metadata: dict = None,
):
    """
    Save a memory about a contact to the vector store.

    Args:
        contact     : Contact's name
        memory_text : The memory to store (will be embedded)
        memory_type : "profile", "conversation", "life_event", "general"
        metadata    : Additional metadata dict

    Example:
        save_memory_to_rag(
            "Rahul Ahmed",
            "Rahul joined Google as a Senior Engineer in March 2024. "
            "He's passionate about AI and open source. Recently got married.",
            memory_type="profile",
        )
    """
    client = _get_client()
    if not client:
        return False

    try:
        collection = client.get_collection("contact_memories")
        doc_id     = f"{contact}_{memory_type}_{date.today().isoformat()}"
        now        = datetime.now().isoformat()

        meta = {
            "contact":     contact,
            "type":        memory_type,
            "date":        date.today().isoformat(),
            "year":        str(date.today().year),
            "created_at":  now,
        }
        if metadata:
            meta.update(metadata)

        # Upsert — update if exists, insert if not
        collection.upsert(
            ids=[doc_id],
            documents=[memory_text],
            metadatas=[meta],
        )

        logger.info("🧠 RAG memory saved for %s (%s)", contact, memory_type)
        return True

    except Exception as e:
        logger.error("❌ RAG save failed for %s: %s", contact, e)
        return False


def save_conversation_log(
    contact: str,
    message_sent: str,
    their_reply: str = "",
    occasion: str = "birthday",
):
    """Save a full conversation exchange to the vector store."""
    client = _get_client()
    if not client:
        return False

    try:
        collection = client.get_collection("conversation_logs")
        doc_id     = f"{contact}_{occasion}_{date.today().isoformat()}"

        text = f"We sent: {message_sent}"
        if their_reply:
            text += f"\nThey replied: {their_reply}"

        collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas={
                "contact":  contact,
                "occasion": occasion,
                "date":     date.today().isoformat(),
                "year":     str(date.today().year),
                "replied":  str(bool(their_reply)),
            },
        )
        logger.info("💬 Conversation logged for %s", contact)
        return True

    except Exception as e:
        logger.error("❌ Conversation log failed: %s", e)
        return False


def save_profile_snapshot(contact: str, profile_info: dict):
    """Save a LinkedIn profile snapshot to the vector store."""
    client = _get_client()
    if not client:
        return False

    try:
        collection = client.get_collection("profile_snapshots")
        doc_id     = f"{contact}_snapshot_{date.today().isoformat()}"

        # Convert profile to natural language
        text_parts = [f"{contact}'s LinkedIn profile as of {date.today().isoformat()}:"]
        if profile_info.get("job_title"):
            text_parts.append(f"Job: {profile_info['job_title']}")
        if profile_info.get("company"):
            text_parts.append(f"Company: {profile_info['company']}")
        if profile_info.get("location"):
            text_parts.append(f"Location: {profile_info['location']}")
        if profile_info.get("shared_interests"):
            text_parts.append(
                f"Interests: {', '.join(profile_info['shared_interests'])}"
            )
        if profile_info.get("additional_notes"):
            text_parts.append(f"Notes: {profile_info['additional_notes']}")

        text = "\n".join(text_parts)

        collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas={
                "contact": contact,
                "date":    date.today().isoformat(),
                "year":    str(date.today().year),
            },
        )
        logger.info("📸 Profile snapshot saved for %s", contact)
        return True

    except Exception as e:
        logger.error("❌ Profile snapshot failed: %s", e)
        return False


# ──────────────────────────────────────────────
# RETRIEVE MEMORY
# ──────────────────────────────────────────────
def retrieve_relevant_memory(
    contact: str,
    query: str = "",
    n_results: int = 3,
) -> list[dict]:
    """
    Retrieve relevant memories for a contact using semantic search.

    Args:
        contact   : Contact's name
        query     : What to search for (e.g. "career achievements")
        n_results : Number of results to return

    Returns:
        List of relevant memory dicts with text and metadata.
    """
    client = _get_client()
    if not client:
        return []

    try:
        collection = client.get_collection("contact_memories")

        # If no query, retrieve all memories for this contact
        search_query = query if query else f"memories about {contact}"

        results = collection.query(
            query_texts=[search_query],
            n_results=min(n_results, 10),
            where={"contact": contact},
        )

        memories = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                dist = results["distances"][0][i] if results.get("distances") else 1.0
                memories.append({
                    "text":       doc,
                    "type":       meta.get("type", "general"),
                    "date":       meta.get("date", ""),
                    "year":       meta.get("year", ""),
                    "relevance":  round(1 - dist, 3),
                })

        logger.info(
            "🔍 Retrieved %d memories for %s (query: '%s')",
            len(memories), contact, query[:40],
        )
        return memories

    except Exception as e:
        logger.error("❌ Memory retrieval failed for %s: %s", contact, e)
        return []


def retrieve_conversation_history(
    contact: str,
    n_results: int = 5,
) -> list[dict]:
    """Retrieve past conversations with a contact."""
    client = _get_client()
    if not client:
        return []

    try:
        collection = client.get_collection("conversation_logs")
        results    = collection.query(
            query_texts=[f"conversation with {contact}"],
            n_results=min(n_results, 10),
            where={"contact": contact},
        )

        conversations = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                conversations.append({
                    "text":     doc,
                    "occasion": meta.get("occasion", ""),
                    "date":     meta.get("date", ""),
                    "year":     meta.get("year", ""),
                    "replied":  meta.get("replied", "False") == "True",
                })
        return conversations

    except Exception as e:
        logger.error("❌ Conversation retrieval failed: %s", e)
        return []


def build_rag_context(contact: str) -> str:
    """
    Build a rich context string from RAG memory for wish generation.
    Combines profile snapshots, past conversations, and general memories.

    Returns:
        A formatted context string for the LLM prompt.
    """
    memories      = retrieve_relevant_memory(contact, n_results=3)
    conversations = retrieve_conversation_history(contact, n_results=2)

    if not memories and not conversations:
        return ""

    parts = [f"MEMORY CONTEXT FOR {contact.upper()}:"]

    if memories:
        parts.append("\n📝 What we know about them:")
        for m in memories:
            year = f" ({m['year']})" if m["year"] else ""
            parts.append(f"  • {m['text']}{year}")

    if conversations:
        parts.append("\n💬 Past interactions:")
        for c in conversations:
            year    = f" ({c['year']})" if c["year"] else ""
            replied = "→ They replied!" if c["replied"] else "→ No reply"
            parts.append(f"  • {c['date']}{year}: {c['text'][:100]}... {replied}")

    context = "\n".join(parts)
    logger.info("🧠 RAG context built for %s (%d chars)", contact, len(context))
    return context


# ──────────────────────────────────────────────
# RAG WISH GENERATOR
# ──────────────────────────────────────────────
async def generate_rag_wish(
    llm,
    name: str,
    profile_info: dict,
    relationship: str = "acquaintance",
) -> str:
    """
    Generate a birthday wish enriched with RAG memory context.

    Args:
        llm          : LangChain LLM instance
        name         : Contact's first name
        profile_info : Current profile data
        relationship : Relationship type

    Returns:
        Memory-enriched wish string.
    """
    from langchain_core.messages import HumanMessage

    # Save current profile snapshot first
    save_profile_snapshot(name, profile_info)

    # Retrieve rich context from vector store
    rag_context = build_rag_context(name)

    job_title = profile_info.get("job_title", "")
    company   = profile_info.get("company", "")
    interests = ", ".join(profile_info.get("shared_interests", []))

    memory_section = f"""
  RICH MEMORY CONTEXT (from vector database):
  {rag_context}

  Use this context to make the wish deeply personal.
  Reference past conversations or known details naturally.
  Example: "Hope the new chapter at [company] has been everything you hoped for!"
""" if rag_context else "  No previous memory found — write a warm first-time wish."

    prompt = f"""
Write a birthday wish for {name}.

Current info:
  Job Title : {job_title or "Unknown"}
  Company   : {company or "Unknown"}
  Interests : {interests or "Unknown"}
  Relationship: {relationship}

{memory_section}

Rules:
  ✅ Start with "Happy Birthday {name}!"
  ✅ Reference something from memory if available
  ✅ Mention their current role naturally
  ✅ 2-3 sentences, warm and genuine
  ✅ 1-2 relevant emoji
  ❌ Don't sound like a template

Reply with ONLY the wish.
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        wish     = response.content.strip().strip('"').strip("'")
        logger.info("✨ RAG wish for %s: %s", name, wish[:60] + "...")

        # Save this interaction to memory
        save_memory_to_rag(
            name,
            f"Sent birthday wish in {date.today().year}: {wish}",
            memory_type="conversation",
        )
        return wish

    except Exception as e:
        logger.error("❌ RAG wish generation failed: %s", e)
        return f"Happy Birthday {name}! 🎂 Wishing you an incredible year ahead!"


# ──────────────────────────────────────────────
# MIGRATION FROM SQLITE MEMORY
# ──────────────────────────────────────────────
def migrate_from_sqlite_memory():
    """
    Migrate existing SQLite memory records to ChromaDB.
    Run once to transfer data from the old memory system.
    """
    import sqlite3 as sq
    import json as jsonlib

    db = Path("agent_history.db")
    if not db.exists():
        logger.info("No SQLite memory to migrate.")
        return 0

    try:
        with sq.connect(db) as conn:
            rows = conn.execute(
                "SELECT contact, year, job_title, company, "
                "life_event, interests, last_wish "
                "FROM contact_memory"
            ).fetchall()
    except Exception:
        logger.info("No contact_memory table found — skipping migration.")
        return 0

    count = 0
    for row in rows:
        contact, year, job_title, company, life_event, interests_json, last_wish = row
        interests = []
        try:
            interests = jsonlib.loads(interests_json) if interests_json else []
        except Exception:
            pass

        text_parts = [f"Memory from {year}:"]
        if job_title and company:
            text_parts.append(f"Working as {job_title} at {company}")
        elif job_title:
            text_parts.append(f"Working as {job_title}")
        if life_event:
            text_parts.append(f"Life event: {life_event}")
        if interests:
            text_parts.append(f"Interests: {', '.join(interests)}")
        if last_wish:
            text_parts.append(f"Last wish sent: {last_wish}")

        memory_text = ". ".join(text_parts)
        save_memory_to_rag(
            contact, memory_text,
            memory_type="profile",
            metadata={"year": str(year), "migrated": "true"},
        )
        count += 1

    logger.info("✅ Migrated %d SQLite memory records to ChromaDB.", count)
    return count