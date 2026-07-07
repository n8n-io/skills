# RAG (retrieval augmented generation)

RAG in n8n is built on the LangChain primitives: document loaders, embeddings, vector stores, retrievers, and (eventually) rerankers. They wire onto agents and chains the same way models and memory do.

## Before you go vector

Not every retrieval problem needs a vector store. Three cheaper alternatives to rule out first:

- **Database or Data Table for exact lookups.** "Look up customer X's record", "fetch issue #1234", "get rows where status = 'open'" are not RAG problems. Use a database query or `n8n-data-tables-official` directly.
- **Live search for freshness.** If you need information that isn't in anything you've indexed (current news, live API state, anything time-sensitive), a search tool (Tavily, etc.) beats RAG.
- **Grep-style / file-browse tools for small or structured sets of documents.** When the set of documents is small enough to list out (a repo, a docs site, a few hundred markdown files), giving the agent list / fetch / search tools and letting it navigate is often simpler than ingesting. As an abstract example, an agent browsing a GitHub repo can be wired with `n8n-nodes-base.githubTool` (list files at a path) plus an HTTP Request Tool against `api.github.com/repos/{owner}/{repo}/contents/{path}` with `Accept: application/vnd.github.raw+json` to fetch raw text. No ingest, no embeddings, full source paths in citations.

Reach for vector RAG when there are too many documents to list out, queries are semantic rather than navigational, and you need similarity-based retrieval at low latency.

## Quickest start: in-memory vector store

The fastest path to a working RAG flow uses the in-memory vector store (`@n8n/n8n-nodes-langchain.vectorStoreInMemory`). It needs no external service, no provisioning, and no extra credentials beyond whichever embedding / chat-model provider you already use. Just drop it into the workflow. Data is lost on workflow restart, so this is right for prototypes, learning, and tests, not production.

Setup at a glance:

- **Ingest workflow**: any trigger that produces documents → Default Data Loader → Vector Store In-Memory (mode: `insert`) with an Embeddings node wired into `ai_embedding`. For manual testing, the Form Trigger with a file-upload field is a quick way to drop in PDFs / CSVs without scripting.
- **Query workflow**: Chat Trigger → Agent → Vector Store In-Memory (mode: `retrieve-as-tool`), with the SAME `memoryKey` value as ingest and the SAME embedding model.

When the data needs to survive restarts or scale beyond a single instance, swap the in-memory node for a persistent vector store (`vectorStoreQdrant`, `vectorStoreSupabase`, etc.). The rest of the wiring stays the same.

n8n ships a starter template that demonstrates the in-memory pattern end-to-end. See [n8n's RAG docs](https://docs.n8n.io/advanced-ai/rag-in-n8n/).

## Vector RAG: the pieces

n8n exposes the LangChain primitives as sub-nodes:

- **Document loaders** (`@n8n/n8n-nodes-langchain.documentDefaultDataLoader`): pull from sources, optionally with metadata. Wires into a vector store node's `ai_document` input.
- **Text splitters** (`textSplitter*`): chunk into retrievable pieces. Default loader can do this inline for simple cases.
- **Embeddings** (`embeddingsOpenAi`, `embeddingsCohere`, etc.): turn chunks into vectors. Wires into `ai_embedding` on both ingest and query sides.
- **Vector stores**: store and query vectors. Start with `vectorStoreInMemory` (no external service, no extra credential). For persistence across restarts, the built-in alternatives are `vectorStoreQdrant`, `vectorStoreSupabase` (Postgres pgvector), and `vectorStorePinecone`. Each has multiple modes: `insert` for ingest, `retrieve-as-tool` for the agent's `ai_tool` slot, and others for direct querying inside a workflow.
- **Vector-store tools (third-party)**: `n8n-nodes-qdrant.qdrantTool` exposes raw Qdrant operations (list collections, scroll, etc.) to the agent. Distinct from the LangChain vector-store node's `retrieve-as-tool` mode, which only does similarity retrieval. Useful when the agent needs to discover what's in the store, not just search it.


## Vector RAG: two workflows

Vector RAG splits cleanly into two workflows, one per direction.

### Ingest workflow

Triggered manually, by schedule, by webhook, or as a sub-workflow tool the agent calls when it wants to add to the store. Shape:

```
[Trigger]
  ->  [Vector Store, mode: 'insert']
        ai_document   <- [Default Data Loader (with metadata)]
        ai_embedding  <- [Embeddings (OpenAI / Cohere / etc.)]
```

**Ingest does not have to be a tool.** Most often it's a separate scheduled workflow that pre-populates the vector store on a cadence (e.g. nightly), or a webhook-triggered workflow invoked by the system that produces the documents. Wire it as an agent tool only when the documents change dynamically based on conversation (the agent learns something it should remember). For static or system-managed document sets, a standalone workflow is simpler and easier to reason about.

The Default Data Loader's `metadata` field is load-bearing: anything you want to filter or display alongside retrieval results (source URL, document type, tenant ID) goes there. Without it, retrieval results are just chunks with no provenance.

### Query workflow

```
[Chat / webhook trigger]
  ->  [Agent]
        ai_tool         <- [Vector Store, mode: 'retrieve-as-tool']
                              ai_embedding <- [Embeddings (same model as ingest)]
        ai_languageModel <- [Chat Model]
        ai_memory       <- [Memory]
```

Wired as `ai_tool`, the vector store becomes a tool the agent calls when it judges retrieval relevant. Wire retrieval directly into the main flow (pre-agent) instead only when every turn requires retrieval, which is rare in practice.

**Embedding model must match.** Whatever model embedded the documents on ingest must also embed the query. Mismatched models produce garbage retrieval. If you change embedding models, re-ingest the documents.

## What's still open

Specific defaults depend too much on context to encode here. Verify against current n8n docs and your team's choices.

### Vector store selection

- **In-memory** (`vectorStoreInMemory`): zero ops, lost on restart. Right for prototypes and tests.
- **Qdrant** (`vectorStoreQdrant`): open-source, self-hostable, fast, mature in n8n. The built-in node covers insert and retrieve. The third-party `qdrantTool` adds raw Qdrant operations as agent tools when similarity search alone isn't enough.
- **Postgres pgvector / Supabase** (`vectorStoreSupabase`): Postgres-based, ideal if you're already running Postgres or on Supabase. SQL-side queries (filter by metadata, join with relational data) compose nicely.
- **Pinecone** (`vectorStorePinecone`): fully managed, per-request pricing.


### Embedding model

OpenAI's `text-embedding-3-large`, Cohere's `embed-v3`, and various open-source models are common. Cost, dimension count, and quality differ, choose carefully upfront to avoid the need to reembed.


### Retrieval-as-tool vs retrieval-before-agent

- **Retrieval-as-tool**: agent decides when retrieval is relevant AND can phrase the query itself (reformulate, decompose, expand the user's wording into something the vector search will actually match). Extra round trip per retrieval, fewer wasted retrievals overall, and a better hit rate per query.
- **Retrieval-before-agent**: simpler, predictable. Pays the retrieval cost every turn AND uses the user's raw input as the query, so the agent can't optimize the search. Vague or conversational user phrasing ("can you remind me how that thing works again?") goes straight into the vector store.

Either works. Tool-based composes better in multi-capability agents (retrieval is one tool among several). Always-retrieve is fine for narrow Q&A bots where every question is a knowledge-base question.

## Cross-references

- For agent fundamentals: parent `SKILL.md`.
- For wiring sub-workflows as tools, including agentic retrieval tool patterns: `SUBWORKFLOW_AS_TOOL.md`.
- For tool naming and descriptions on retrieval tools: `TOOLS.md`.
- For Data Tables (sometimes a viable alternative to a vector store for small structured data): `n8n-data-tables-official` SKILL.