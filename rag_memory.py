"""
rag_memory.py — Updated with Conversation Memory (Context-aware Reply)
"""

import logging
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
CHROMA_DIR = Path("chroma_db")


def init_rag_memory():
    try:
        import chromadb
        from chromadb.config import Settings
        client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        client.get_or_create_collection("contact_memories",
                                         metadata={"hnsw:space": "cosine"})
        client.get_or_create_collection("conversation_logs",
                                         metadata={"hnsw:space": "cosine"})
        client.get_or_create_collection("profile_snapshots",
                                         metadata={"hnsw:space": "cosine"})
        logger.info("🧠 RAG Memory initialized at: %s", CHROMA_DIR)
        return client
    except ImportError:
        logger.error("❌ ChromaDB not installed. Run: pip install chromadb sentence-transformers")
        return None
    except Exception as e:
        logger.error("❌ RAG Memory init failed: %s", e)
        return None


def _get_client():
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


def save_memory_to_rag(contact, memory_text, memory_type="general", metadata=None):
    client = _get_client()
    if not client:
        return False
    try:
        collection = client.get_collection("contact_memories")
        doc_id     = f"{contact}_{memory_type}_{date.today().isoformat()}"
        now        = datetime.now().isoformat()
        meta = {
            "contact": contact, "type": memory_type,
            "date": date.today().isoformat(),
            "year": str(date.today().year), "created_at": now,
        }
        if metadata:
            meta.update(metadata)
        collection.upsert(ids=[doc_id], documents=[memory_text], metadatas=[meta])
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
    """
    Save a full conversation exchange to the vector store.
    Called after EVERY wish/reply to build conversation history.
    """
    client = _get_client()
    if not client:
        return False
    try:
        collection = client.get_collection("conversation_logs")

        # Unique ID per conversation turn
        doc_id = f"{contact}_{occasion}_{date.today().isoformat()}_{datetime.now().strftime('%H%M%S')}"

        # Build natural language conversation text
        text = f"[{date.today().isoformat()}] {occasion.upper()} conversation with {contact}:\n"
        text += f"We sent: {message_sent}"
        if their_reply:
            text += f"\nThey replied: {their_reply}"
            text += f"\n(Reply received — they responded to our {occasion} message)"

        collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas={
                "contact":      contact,
                "occasion":     occasion,
                "date":         date.today().isoformat(),
                "year":         str(date.today().year),
                "replied":      str(bool(their_reply)),
                "message_sent": message_sent[:200],
                "their_reply":  their_reply[:200] if their_reply else "",
            },
        )
        logger.info("💬 Conversation logged for %s (occasion: %s, replied: %s)",
                    contact, occasion, bool(their_reply))
        return True
    except Exception as e:
        logger.error("❌ Conversation log failed: %s", e)
        return False


def save_profile_snapshot(contact, profile_info):
    client = _get_client()
    if not client:
        return False
    try:
        collection = client.get_collection("profile_snapshots")
        doc_id     = f"{contact}_snapshot_{date.today().isoformat()}"
        text_parts = [f"{contact}'s LinkedIn profile as of {date.today().isoformat()}:"]
        if profile_info.get("job_title"):
            text_parts.append(f"Job: {profile_info['job_title']}")
        if profile_info.get("company"):
            text_parts.append(f"Company: {profile_info['company']}")
        if profile_info.get("location"):
            text_parts.append(f"Location: {profile_info['location']}")
        if profile_info.get("shared_interests"):
            text_parts.append(f"Interests: {', '.join(profile_info['shared_interests'])}")
        if profile_info.get("additional_notes"):
            text_parts.append(f"Notes: {profile_info['additional_notes']}")
        text = "\n".join(text_parts)
        collection.upsert(
            ids=[doc_id], documents=[text],
            metadatas={"contact": contact, "date": date.today().isoformat(),
                       "year": str(date.today().year)},
        )
        logger.info("📸 Profile snapshot saved for %s", contact)
        return True
    except Exception as e:
        logger.error("❌ Profile snapshot failed: %s", e)
        return False


def retrieve_relevant_memory(contact, query="", n_results=3):
    client = _get_client()
    if not client:
        return []
    try:
        collection   = client.get_collection("contact_memories")
        search_query = query if query else f"memories about {contact}"
        results      = collection.query(
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
                    "text":      doc,
                    "type":      meta.get("type", "general"),
                    "date":      meta.get("date", ""),
                    "year":      meta.get("year", ""),
                    "relevance": round(1 - dist, 3),
                })
        logger.info("🔍 Retrieved %d memories for %s", len(memories), contact)
        return memories
    except Exception as e:
        logger.error("❌ Memory retrieval failed for %s: %s", contact, e)
        return []


def retrieve_conversation_history(contact, n_results=10) -> list[dict]:
    """
    Retrieve full conversation history for a contact.
    Sorted by date — newest first.
    Used for context-aware replies.
    """
    client = _get_client()
    if not client:
        return []
    try:
        collection = client.get_collection("conversation_logs")
        results    = collection.query(
            query_texts=[f"all conversations with {contact}"],
            n_results=min(n_results, 50),
            where={"contact": contact},
        )
        conversations = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                conversations.append({
                    "text":         doc,
                    "occasion":     meta.get("occasion", ""),
                    "date":         meta.get("date", ""),
                    "year":         meta.get("year", ""),
                    "replied":      meta.get("replied", "False") == "True",
                    "message_sent": meta.get("message_sent", ""),
                    "their_reply":  meta.get("their_reply", ""),
                })
        # Sort by date descending
        conversations.sort(key=lambda x: x["date"], reverse=True)
        return conversations
    except Exception as e:
        logger.error("❌ Conversation retrieval failed: %s", e)
        return []


def build_rag_context(contact: str) -> str:
    """
    Build a rich context string from RAG memory.
    Combines profile snapshots, past conversations, and general memories.
    Used for context-aware wish/reply generation.
    """
    memories      = retrieve_relevant_memory(contact, n_results=3)
    conversations = retrieve_conversation_history(contact, n_results=5)

    if not memories and not conversations:
        return ""

    parts = [f"MEMORY CONTEXT FOR {contact.upper()}:"]

    if memories:
        parts.append("\n📝 What we know about them:")
        for m in memories:
            year = f" ({m['year']})" if m["year"] else ""
            parts.append(f"  • {m['text']}{year}")

    if conversations:
        parts.append("\n💬 Conversation history:")
        for c in conversations[:5]:
            year    = f" ({c['year']})" if c["year"] else ""
            replied = "→ They replied!" if c["replied"] else "→ No reply"
            occasion = c["occasion"].replace("_", " ").title()
            parts.append(
                f"  • [{c['date']}{year}] {occasion}: "
                f"{c['message_sent'][:80]}... {replied}"
            )
            if c["their_reply"]:
                parts.append(f"    Their reply: \"{c['their_reply'][:80]}\"")

    context = "\n".join(parts)
    logger.info("🧠 RAG context built for %s (%d chars)", contact, len(context))
    return context


def build_context_aware_reply_prompt(
    contact: str,
    their_message: str,
    occasion: str = "birthday",
) -> str:
    """
    Build a context-aware reply prompt using full conversation history.
    Called before generating any reply to inject past context.
    """
    context = build_rag_context(contact)
    if not context:
        return ""

    return f"""
  CONVERSATION HISTORY CONTEXT:
  {context}

  Use this history to make your reply feel natural and continuous.
  Examples:
  - If they replied last year → "Great to hear from you again {contact}!"
  - If they mentioned something specific → reference it naturally
  - If this is first interaction → "Thank you so much for the lovely wishes!"
  - Never directly quote old messages — reference them subtly
"""


async def generate_rag_wish(llm, name, profile_info, relationship="acquaintance"):
    from langchain_core.messages import HumanMessage
    save_profile_snapshot(name, profile_info)
    rag_context = build_rag_context(name)
    job_title   = profile_info.get("job_title", "")
    company     = profile_info.get("company", "")
    interests   = ", ".join(profile_info.get("shared_interests", []))
    memory_section = f"""
  RICH MEMORY CONTEXT (from vector database):
  {rag_context}
  Use this context to make the wish deeply personal.
""" if rag_context else "  No previous memory found — write a warm first-time wish."

    prompt = f"""
Write a birthday wish for {name}.

Current info:
  Job Title    : {job_title or "Unknown"}
  Company      : {company or "Unknown"}
  Interests    : {interests or "Unknown"}
  Relationship : {relationship}

{memory_section}

Rules:
  ✅ Start with "Happy Birthday {name}!"
  ✅ Reference something from memory if available
  ✅ 2-3 sentences, warm and genuine
  ✅ 1-2 relevant emoji
  ❌ Don't sound like a template

Reply with ONLY the wish.
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        wish     = response.content.strip().strip('"').strip("'")
        logger.info("✨ RAG wish for %s: %s", name, wish[:60] + "...")
        save_memory_to_rag(name,
                           f"Sent birthday wish in {date.today().year}: {wish}",
                           memory_type="conversation")
        return wish
    except Exception as e:
        logger.error("❌ RAG wish generation failed: %s", e)
        return f"Happy Birthday {name}! 🎂 Wishing you an incredible year ahead!"


def migrate_from_sqlite_memory():
    import sqlite3 as sq
    import json as jsonlib
    db = Path("agent_history.db")
    if not db.exists():
        return 0
    try:
        with sq.connect(db) as conn:
            rows = conn.execute(
                "SELECT contact, year, job_title, company, "
                "life_event, interests, last_wish FROM contact_memory"
            ).fetchall()
    except Exception:
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
        save_memory_to_rag(contact, ". ".join(text_parts),
                           memory_type="profile",
                           metadata={"year": str(year), "migrated": "true"})
        count += 1
    logger.info("✅ Migrated %d SQLite memory records to ChromaDB.", count)
    return count