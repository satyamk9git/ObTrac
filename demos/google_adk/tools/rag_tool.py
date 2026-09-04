"""
RAG lookup tool — simulates document retrieval for the rag_qa_agent, chunked
from test_documents/nimbusdb_handbook.txt (a fictional product handbook used
across ObTrac's demo apps as a shared "chat with this document" test fixture).
In production replace the in-memory store with a real vector DB.
"""

import random
from google.adk.tools import ToolContext
from obtrac_sdk import trace

# Simulated document store: topic → chunks, sourced from
# test_documents/nimbusdb_handbook.txt's own section breakdown.
_DOC_STORE = {
    "pricing": [
        "NimbusDB Starter tier is $0/month: single region, shared compute, up to 1GB storage, 25M requests/month included, no SLA.",
        "NimbusDB Growth tier is $89/month base + usage: dedicated compute, $0.25/GB above 10GB, $0.90 per million requests above 100M, 99.9% uptime SLA.",
        "NimbusDB Enterprise starts around $2,400/month: multi-region, 99.99% uptime SLA, dedicated Slack channel, 1-hour Sev-1 response.",
        "A 14-day free trial of the Enterprise tier is available with no credit card required to start.",
    ],
    "architecture": [
        "NimbusDB uses a disaggregated storage-and-compute architecture with three layers: Query Router, Storage Engine (Cascade), and Consensus (Ferry).",
        "Cascade is an LSM-tree storage engine grouping documents into ~2GB shards, with a typical write amplification factor of 3.1x.",
        "Ferry is a Raft-based consensus protocol; each shard is replicated across 3 or 5 nodes, customer configurable.",
        "Cross-region replication is asynchronous by default (120-400ms typical lag) but can be switched to synchronous per collection.",
    ],
    "consistency": [
        "NimbusDB supports four consistency modes: STRONG, BOUNDED_STALENESS, SESSION, and EVENTUAL.",
        "STRONG consistency reads always reflect the latest committed write, served only by the shard leader — highest latency.",
        "BOUNDED_STALENESS defaults to a 5-second or 100-version staleness window, whichever comes first.",
        "Changing a collection's consistency mode takes up to 60 seconds to fully propagate, with no downtime required.",
    ],
    "cdc": [
        "Change Data Capture (CDC) streams every write in near-real-time to NimbusStream, Kafka, or a webhook.",
        "NimbusStream delivery is typically under 200ms from commit to delivery.",
        "CDC is NOT enabled by default — turning it on adds approximately 4-7% write overhead.",
        "Webhook CDC delivery is at-least-once with exponential backoff retry, up to 6 attempts over 24 hours.",
    ],
    "security": [
        "NimbusDB Enterprise is SOC 2 Type II certified, most recent report dated May 2026, and supports HIPAA deployments under a signed BAA.",
        "NimbusDB is NOT currently FedRAMP authorized — targeted for late 2027 with no committed date.",
        "Encryption at rest is AES-256; Enterprise customers can bring their own keys (BYOK) via AWS KMS or GCP Cloud KMS.",
        "TLS 1.3 is required for client connections; TLS 1.2 is accepted but deprecated.",
    ],
    "limitations": [
        "Maximum NimbusDB document size is 4MB, a hard limit that is not configurable.",
        "Maximum of 64 secondary indexes per collection.",
        "Transactions span at most 1 shard — there is no cross-shard multi-document transaction support as of v4.2.",
        "Point-in-time restore: 35 days on Enterprise, 7 days on Growth, not available on Starter.",
    ],
    "support": [
        "Enterprise Sev-1 (production down) response time is 1 hour; Growth is 4 hours business hours only; Starter has no SLA.",
        "Enterprise SLA credits are 10% of monthly fee per 0.1% below the 99.99% uptime target, capped at 50% of that month's fee.",
    ],
    "migration": [
        "nimbus-migrate is a free migration tool supporting MongoDB (via oplog tailing), PostgreSQL JSONB columns, and flat JSON/CSV/BSON dumps.",
        "A typical 100GB MongoDB migration takes 6-10 hours depending on document complexity and target shard count.",
        "Nimbus Systems offers free hands-on migration support to Enterprise customers for migrations under 1TB.",
    ],
    "query": [
        "NimbusDB queries use NQL (Nimbus Query Language), a JSON-based syntax similar to MongoDB's query language.",
        "NQL's $join operator performs a bounded lookup join across collections, maximum 3 hops — not a general relational join.",
        "Aggregation pipelines are limited to 25 stages per query; exceeding this returns error code NQL-4091.",
    ],
    "default": [
        "No specific documents found. Returning general knowledge.",
        "Try asking about: pricing, architecture, consistency, CDC, security, limitations, support, migration, or query language.",
    ],
}


@trace(name="rag_lookup", span_type="retrieval")
def rag_lookup(query: str, top_k: int = 3, tool_context: ToolContext = None) -> dict:
    """
    Retrieve relevant document chunks for a query (simulated vector search).

    Args:
        query: User's question.
        top_k: Number of chunks to return (default 3).
        tool_context: Injected by ADK — session_id auto-detected by ObTrac.

    Returns:
        dict with 'chunks' list and 'source' key.
    """
    q = query.lower()
    chunks = _DOC_STORE["default"]
    for topic, docs in _DOC_STORE.items():
        if topic in q:
            chunks = docs
            break

    selected = random.sample(chunks, min(top_k, len(chunks)))
    return {
        "query": query,
        "chunks": selected,
        "chunk_count": len(selected),
        "source": "in-memory-store (replace with real vector DB)",
    }
