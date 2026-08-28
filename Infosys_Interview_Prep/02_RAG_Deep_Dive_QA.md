# 02 — RAG Deep Dive Interview Q&A

**Focus:** Retrieval-Augmented Generation end-to-end — ingestion, chunking, embeddings, indexing, retrieval, reranking, evaluation, production failure modes.  
**Use with:** VoXgent.AI (LangChain / LangGraph / Pinecone) stories from your resume.

---

## How to use this file

| Label | Meaning |
|-------|---------|
| **Say this** | Speak this in the interview — simple English, like a developer explaining to a panel |
| **Compare** | Short side-by-side when they ask "why this vs that" |
| **Follow-up** | What they ask next — answer in one or two lines |

**Tip:** Lead with the idea, then one VoXgent example (healthcare policy lookup, sales script, support FAQ, Pinecone + LangGraph).

---

## A. Fundamentals & Architecture

### Q1. Explain RAG in one minute for a non-GenAI manager.

**Say this:**

> RAG means the AI answers using your company documents, not just what it learned in training. When someone asks a question, we search the knowledge base, pull the best matching passages, and give those to the model as context. The model then writes an answer based on that text. That is how VoXgent voice agents stay accurate for healthcare policies, sales scripts, and support docs — they read from the client's own data instead of making things up.

**Follow-up:**

1. **Why not just train the model on our docs?**  
   **Say this:** > Docs change often. RAG lets you update the knowledge base without retraining. Training is slow and expensive; RAG is faster to ship and easier to fix when a policy changes.

2. **Does RAG stop all wrong answers?**  
   **Say this:** > No. It cuts down hallucinations a lot, but bad retrieval or a weak prompt can still cause errors. That is why we test retrieval first and tell the agent to say "I don't know" when context is missing.

---

### Q2. Draw / narrate the classic RAG architecture.

**Say this:**

> Offline side: documents go through parse, chunk, embed, and upsert into Pinecone. Online side: user speaks or types a question, we embed the query, search the index, optionally rerank, pack the top chunks into a prompt, and the LLM generates the answer with citations. On VoXgent we also had query rewrite, tenant filters, tool calls, and LangGraph loops on top of the basic flow.

**Compare:**

> **Offline:** heavy work done once or on a schedule — parsing, chunking, embedding.  
> **Online:** must be fast — embed query, retrieve, prompt, generate. Voice agents like VoXgent need the online path under a few seconds.

**Follow-up:**

1. **Where does LangGraph fit?**  
   **Say this:** > After retrieval. If search is weak, the graph can rewrite the query and try again, or branch to a tool call or human transfer instead of one straight generate step.

2. **What optional steps do you mention in an interview?**  
   **Say this:** > Hybrid search, reranking, context compression, conversation-aware query rewrite, evaluation logging — we used several of these in production VoXgent flows.

---

### Q3. Naive RAG vs Advanced RAG vs Modular / Agentic RAG.

**Say this:**

> Naive RAG is retrieve top-k, stuff into prompt, generate — fine for a demo or small FAQ. Advanced RAG adds query rewrite, hybrid search, reranking, compression, and citations — that is what you need for production chat or voice. Modular or agentic RAG means a router or graph decides when to retrieve, when to call a tool, or when to loop again. VoXgent was advanced plus agentic: Pinecone RAG plus LangGraph for multi-step voice workflows.

**Compare:**

> **Naive:** one search, one answer — simple, breaks on hard queries.  
> **Advanced:** better recall and cleaner context — production default.  
> **Agentic:** retrieve, tool, retry, hand off — fits VoXgent healthcare and sales flows.

**Follow-up:**

1. **Which level did VoXgent use?**  
   **Say this:** > Not naive. We had tenant filters, reranking on some clients, tool calling to Salesforce and EMR, and LangGraph loops for retry and human transfer.

2. **When is naive RAG enough?**  
   **Say this:** > Internal prototype, fixed small FAQ, or proof of concept before you invest in eval and hybrid search.

---

### Q4. When would you *not* use RAG?

**Say this:**

> Skip RAG when the task is about tone or format only — prompt or fine-tune is enough. Skip it when there are no external facts, like pure math reasoning. Skip it when the whole FAQ fits in the prompt and never changes. Skip it when latency budget is too tight and you cannot afford search. Also skip it if you are not allowed to index the data legally. On VoXgent we always needed RAG because client knowledge was large, private, and updated often.

**Compare:**

> **RAG:** changing enterprise facts, private docs, need citations.  
> **Fine-tune / prompt:** style, fixed behavior, no doc lookup.  
> **Long context:** few docs, temporary — paste into prompt instead of building an index.

**Follow-up:**

1. **What about long-context models with a 1M token window?**  
   **Say this:** > Still expensive and slow at runtime, and hard to keep fresh. RAG picks only relevant chunks — better for voice latency and for healthcare where you need source citations.

---

### Q5. Online vs offline RAG components.

**Say this:**

> Offline is ingestion: parse documents, chunk, embed in batches, upsert to Pinecone, track versions. Online is query time: embed the question, retrieve with filters, optional rerank, build prompt, call LLM, log results. Never block a live call on heavy re-ingestion — run ingestion in async workers or queues. On VoXgent, doc updates went through background jobs; the voice agent always hit the online path.

**Compare:**

> **Offline:** throughput and correctness of index — can take minutes.  
> **Online:** latency-sensitive — every millisecond counts on a live Twilio call.

**Follow-up:**

1. **How fast must new docs appear in search?**  
   **Say this:** > Define an SLA with the client — often 5 to 15 minutes for async ingest. Critical policy updates can use a fast-path upsert. We surfaced "last updated" on some healthcare flows when staleness mattered.

---

## B. Document Ingestion & Parsing

### Q6. How do you ingest PDFs, DOCX, HTML, and tables?

**Say this:**

> Detect file type first. PDFs: use a layout-aware parser; scanned PDFs need OCR. DOCX: extract text with headings preserved. HTML: strip nav and ads, keep headings and body. Tables: convert to Markdown or row text so numbers stay tied to column headers — never flatten a table into one broken sentence. Store source, page, and section in metadata on every chunk. VoXgent pipelines tagged domain — healthcare, sales, support — so retrieval could filter by client and use case.

**Follow-up:**

1. **What breaks most often in enterprise PDFs?**  
   **Say this:** > Multi-column layouts, headers and footers repeated on every page, and tables split across pages. Good parsing and structure-aware chunking fix most of this.

2. **Do you index raw files or extracted text?**  
   **Say this:** > Extracted text plus metadata. Raw PDF bytes are not searchable with text embeddings. Keep the source URI so citations point back to the original doc.

---

### Q7. Scanned PDFs with handwriting / diagrams — how do you RAG them?

**Say this:**

> Treat it as a multimodal pipeline. OCR for printed text. A handwriting model for notes if needed. A vision model to caption charts and diagrams — index the caption as text. Use table extractors for grids. Keep page and section metadata. Test on messy scans — eval on clean digital PDFs hides real failures. Healthcare clients often send scanned forms; VoXgent-style pipelines must handle that or flag low-confidence pages for human review.

**Compare:**

> **Clean digital PDF:** text extraction only — fast and cheap.  
> **Scanned / mixed:** OCR + captions — slower ingest, needed for real enterprise corpora.

**Follow-up:**

1. **Do you embed the image or the caption?**  
   **Say this:** > For voice RAG we usually indexed caption plus OCR text as text chunks. Full multimodal embeddings are possible but add cost and complexity.

---

### Q8. What metadata should every chunk carry?

**Say this:**

> At minimum: chunk_id, doc_id, tenant_id, source URI, title, page or section, created_at, doc_version, domain like healthcare or sales, and ACL or sensitivity flags. Metadata powers filters, citations, deletes, and tenant isolation. On VoXgent every Pinecone query included tenant_id from auth — metadata was not optional decoration, it was security.

**Follow-up:**

1. **What happens if metadata is missing?**  
   **Say this:** > You cannot filter by client, cannot cite sources properly, and cannot delete old versions cleanly. Cross-tenant leakage becomes possible — that is a production incident, not a small bug.

2. **Effective date for policies?**  
   **Say this:** > Yes for healthcare and compliance docs — store effective_date and doc_version so the model prefers the newest policy when two chunks conflict.

---

### Q9. How do you handle document updates and deletes?

**Say this:**

> Upsert by doc_id: delete all vectors with that doc_id, re-chunk the new version, re-embed, insert fresh vectors. Use a soft-delete flag if audit needs the old version. Bump doc_version for rollback. Never leave orphan chunks from an old PDF sitting in the index — stale healthcare policy in search is worse than a brief ingest delay.

**Compare:**

> **Delete + re-insert:** simple, correct — our default on VoXgent.  
> **In-place vector update:** only if chunk boundaries did not change — rare in practice.

**Follow-up:**

1. **Partial update — one section changed?**  
   **Say this:** > If you chunk by section, delete vectors for that section only and re-embed just those chunks. Full doc re-chunk is safer when structure is messy.

---

### Q10. Multi-tenant RAG — how do you isolate clients?

**Say this:**

> Application auth resolves tenant_id from the token. Every Pinecone query must include a metadata filter on tenant_id — or use separate namespaces per tenant. Never trust the prompt saying "only use Client A docs." Test cross-tenant leakage in CI: query as Tenant A must never return Tenant B chunks. VoXgent served multiple enterprise clients on one platform — this was non-negotiable.

**Compare:**

> **Namespace per tenant:** hard wall — good for big clients.  
> **Shared index + metadata filter:** flexible — what we used with mandatory filter on every query.

**Follow-up:**

1. **Can the LLM leak data across tenants?**  
   **Say this:** > Only if retrieval leaks first. Fix at the database filter layer. Prompt instructions alone are not security.

---

## C. Chunking (high interview density)

### Q11. Why chunk at all?

**Say this:**

> Embedding models and context windows have limits. If you embed a whole 200-page manual as one vector, you lose detail — the vector becomes an average of everything. Chunks create small units of meaning that search can hit precisely. Bad chunking means good models still give wrong answers. On VoXgent, chunk quality mattered as much as model choice for support and sales scripts.

**Follow-up:**

1. **Why not put the full doc in a long-context prompt?**  
   **Say this:** > Too slow and costly for voice, and the model still struggles to find the right paragraph in a huge blob. Retrieval picks the relevant pieces first.

---

### Q12. Chunking strategies — name and trade-offs.

**Say this:**

> Fixed size splits by token count with overlap — simple but can cut mid-sentence. Recursive character splits on paragraphs and sentences — more structure-aware. Semantic chunking splits when embedding similarity drops — topic-coherent but costs more compute. Document-structure chunking uses headers and sections — great for manuals. Parent-child stores small chunks for search and expands to a parent section for generation. Sentence-window keeps a center sentence plus neighbors. On VoXgent we leaned structure-aware and fixed-size with overlap, tuned per client domain.

**Compare:**

> **Fixed size:** fast to build, may break meaning at boundaries.  
> **Structure-aware:** better for policies and manuals — healthcare clients loved section-based chunks.  
> **Parent-child:** best precision plus context — more storage and code.

**Follow-up:**

1. **Which strategy for FAQ vs policy manual?**  
   **Say this:** > FAQ: one question-answer pair per chunk. Policy manual: split by section headers, maybe parent-child for long clauses.

---

### Q13. How do you choose chunk size and overlap for a voice agent?

**Say this:**

> Voice needs low latency and tight context — no room for ten huge chunks. Start around 300 to 600 tokens with 10 to 20 percent overlap. Prefer structure-aware splits for policies so you do not cut mid-clause. Measure on eval: if answers miss facts on chunk boundaries, increase overlap or chunk size. If answers are noisy, shrink chunks and add reranking. VoXgent voice calls had a hard token budget — we kept k small and chunks medium.

**Compare:**

> **Text chat:** can use larger k and bigger chunks.  
> **Voice (VoXgent):** smaller k, compression, skip rerank if over budget.

**Follow-up:**

1. **Typical starting numbers?**  
   **Say this:** > 400 tokens, 15 percent overlap, k equals 5 before rerank down to 3 for the prompt — then tune on golden questions.

---

### Q14. What is parent-child / hierarchical chunking?

**Say this:**

> You index small child chunks for precise search. When a child chunk matches, you pull the larger parent section into the prompt for generation. Search stays sharp; the model still sees full context around the hit. Good for long healthcare policies where the exact sentence matters for retrieval but the whole section matters for the answer.

**Compare:**

> **Flat chunks only:** simpler storage — may miss context around the hit.  
> **Parent-child:** extra index fields and lookup logic — better answers on long docs.

**Follow-up:**

1. **Do you embed both parent and child?**  
   **Say this:** > Usually embed children for search. Parent text is stored in metadata or a separate store and fetched after a child hit.

---

### Q15. Chunk overlap — why and risks?

**Say this:**

> Overlap keeps facts that sit on a chunk boundary from getting lost — half the sentence in one chunk, half in another. Without overlap, search might miss both. Risk: near-duplicate chunks fill top-k with the same paragraph repeated — wastes prompt tokens and confuses the model. Fix with dedupe, MMR diversification, or lower overlap if redundancy shows up in logs.

**Follow-up:**

1. **How much overlap is too much?**  
   **Say this:** > Above 25 to 30 percent you often see duplicate hits without much recall gain. Tune on retrieval metrics, not a blog default.

---

## D. Embeddings

### Q16. What is an embedding model? Same model at index and query?

**Say this:**

> An embedding model turns text into a dense vector — a list of numbers capturing meaning. Similar meanings sit close together in vector space. You must use the same model and same version for documents at index time and queries at search time. Mixing models breaks the space — cosine scores become meaningless. VoXgent used one embedding model end to end on Pinecone.

**Compare:**

> **Same model + version:** required — production rule.  
> **Different models:** only if you re-embed the entire corpus when you switch.

**Follow-up:**

1. **What if you upgrade the embedding model?**  
   **Say this:** > Full re-embed and re-upsert all chunks into a new index or namespace. Blue-green cutover when ready. Never mix old and new vectors in one search.

---

### Q17. Cosine vs dot product vs L2.

**Say this:**

> Cosine similarity measures the angle between vectors — direction, not length. Dot product is related; for L2-normalized vectors, cosine and dot product rank the same and dot is slightly faster. L2 distance is straight-line Euclidean distance — lower means closer. Most text embedding APIs return normalized vectors, so cosine or dot product is standard. Pinecone defaults work fine for our VoXgent text RAG.

**Compare:**

> **Cosine / dot:** standard for normalized text embeddings.  
> **L2:** common in some image or raw vector setups — check your model docs.

**Follow-up:**

1. **Does Pinecone use cosine?**  
   **Say this:** > Configure metric at index creation — cosine, dot product, or Euclidean. Match what your embedding model recommends.

---

### Q18. Embedding dimensions and storage cost.

**Say this:**

> Higher dimensions like 3072 vs 1536 can capture more nuance but cost more storage, RAM, and query latency. Some models support Matryoshka — train once, truncate dimensions for cheaper storage with a small quality hit. Pick dimensions once and keep them consistent across the index. At VoXgent scale, batching and right-sized dims mattered for ingest cost on large client corpora.

**Follow-up:**

1. **When would you pay for higher dims?**  
   **Say this:** > When eval shows clear retrieval gains on domain jargon — medical codes, SKU names — and latency budget allows it. Otherwise start mid-tier and measure.

---

### Q19. Batch embeddings in production.

**Say this:**

> Never embed one chunk per HTTP call at ingest — too slow and you hit rate limits. Batch 50 to 200 texts per request, respect provider rate limits, retry with backoff, and make upserts idempotent so retries do not duplicate vectors. Batching cut VoXgent ingest time sharply on large sales and support doc drops.

**Follow-up:**

1. **What if one text in a batch fails?**  
   **Say this:** > Retry the batch or split binary search to find the bad input — often empty string or text over token limit. Log chunk_id and skip or fix at source.

---

### Q20. Domain-specific vocabulary problem.

**Say this:**

> Generic embeddings miss rare terms — ICD-10 codes, internal SKU names, client acronyms. Fixes: hybrid search with BM25 for exact token match, metadata filters by domain, synonym maps in query rewrite, or domain-tuned embeddings if eval proves the gap. VoXgent healthcare flows often paired dense Pinecone search with keyword-style hybrid for medical codes and product IDs.

**Compare:**

> **Dense only:** great for natural language — weak on exact codes.  
> **Hybrid dense + sparse:** enterprise default when IDs and jargon matter.

**Follow-up:**

1. **Fine-tune the embedding model?**  
   **Say this:** > Last resort — expensive. Try hybrid and query rewrite first. Fine-tune embeddings only with labeled pairs and clear retrieval lift on eval.

---

## E. Vector Index & ANN

### Q21. Exact vs Approximate Nearest Neighbor (ANN).

**Say this:**

> Exact search compares the query to every vector — accurate but O of N, too slow at millions of vectors. ANN uses structures like HNSW or IVF to find approximate neighbors in log time with a tiny recall trade-off. Production Pinecone-scale RAG uses ANN. For a toy index with 500 chunks, exact is fine; for VoXgent client corpora at scale, ANN is required.

**Compare:**

> **Exact (flat):** 100 percent recall — small indexes only.  
> **ANN:** near-perfect recall at speed — production default.

**Follow-up:**

1. **How do you know ANN recall is good enough?**  
   **Say this:** > Run eval: compare top-k from ANN vs brute force on a sample. Tune index params if critical docs drop out of top-k.

---

### Q22. What is HNSW?

**Say this:**

> HNSW is Hierarchical Navigable Small World — a graph-based index with multiple layers. Search starts at coarse layers and drills down to fine neighbors — logarithmic time in practice. Memory-heavy but great latency and recall balance for RAG. Pinecone and many vector DBs use HNSW or similar under the hood.

**Follow-up:**

1. **Trade-off vs IVF?**  
   **Say this:** > HNSW: higher memory, lower latency, strong recall. IVF: clusters vectors, faster build, can miss edge cases if clusters are wrong — pick based on scale and SLA.

---

### Q23. Why Pinecone in VoXgent? Alternatives?

**Say this:**

> Pinecone is managed — no ops cluster for us while shipping voice agents. Strong metadata filtering for tenant_id and domain, good latency at scale, simple LangChain integration. Alternatives: FAISS self-hosted, Chroma for prototypes, Qdrant, Weaviate, Milvus, pgvector if the client already lives on Postgres. We chose Pinecone to move fast on RAG; Infosys clients may mandate their own stack — same patterns, different backend.

**Compare:**

> **Pinecone:** managed, fast filter queries — VoXgent choice.  
> **pgvector:** good when data already in Postgres — fewer moving parts.  
> **FAISS:** max control, you own ops.

**Follow-up:**

1. **Would you pick Pinecone again?**  
   **Say this:** > For a startup shipping fast, yes. For a client with strict data residency, I would match their approved cloud and use Qdrant, Weaviate, or pgvector on their infra.

---

### Q24. Namespaces vs metadata filters.

**Say this:**

> Namespace is a hard partition inside Pinecone — separate index slice per tenant or environment like prod vs staging. Metadata filter is a query-time predicate like domain equals healthcare. Often combine both: namespace per big client, filters inside for domain, doc type, or date. VoXgent used metadata filters on tenant_id on every query even in a shared index.

**Compare:**

> **Namespace:** coarse isolation — delete whole tenant easy.  
> **Metadata filter:** flexible, many dimensions — must enforce in code on every query.

**Follow-up:**

1. **Can you skip filters if namespaces exist?**  
   **Say this:** > Only if namespace is guaranteed unique per tenant at routing layer. Still filter by domain or ACL inside when multiple doc types share a namespace.

---

### Q25. Index freshness SLA.

**Say this:**

> Define max staleness with the client — e.g. new docs searchable within 5 to 15 minutes after upload. Run ingestion as async workers with upsert. Critical updates can use a synchronous fast path. Show "knowledge last updated" in UI or call summary when healthcare clients care about policy date. VoXgent outbound campaigns assumed index was fresh before calls went out — ingest jobs completed before dial windows.

**Follow-up:**

1. **User uploads doc but bot still gives old answer?**  
   **Say this:** > Check ingest queue lag, doc_version in metadata, and cache invalidation. Old answer often means old vectors still in index or cached retrieval result.

---

## F. Query-time Retrieval

### Q26. Walk through query-time step by step.

**Say this:**

> One: auth and resolve tenant_id. Two: optional query rewrite using chat history. Three: embed the query. Four: vector search with metadata filters. Five: optional hybrid sparse fusion. Six: optional cross-encoder rerank. Seven: pack or compress context to fit token budget. Eight: build prompt and call LLM. Nine: return answer with citations and log everything. VoXgent LangGraph wrapped these steps with branches for tools and human transfer.

**Follow-up:**

1. **Which steps do you parallelize?**  
   **Say this:** > Embed plus metadata lookup can overlap with other prep. Hybrid dense and sparse can run in parallel then fuse. Do not parallelize rerank before you have candidate chunks.

---

### Q27. What is top-k? How do you choose k?

**Say this:**

> Top-k means return the k nearest chunks to the query embedding. k too small — you miss the fact. k too large — noise, higher cost, slower prompt. Start k equals 3 to 8 for voice, 5 to 20 for text chat, retrieve more if you rerank down to final 3 to 5. VoXgent voice often retrieved 5, reranked to 3, then generated.

**Compare:**

> **Low k:** fast, precise if retrieval is good — voice default.  
> **High k + rerank:** better recall — text chat and complex support tickets.

**Follow-up:**

1. **Same k for healthcare and sales?**  
   **Say this:** > Tune per domain on eval. Healthcare policies may need slightly higher k before rerank; sales scripts were often shorter and worked with smaller k.

---

### Q28. Similarity score thresholds.

**Say this:**

> Drop chunks below a similarity threshold so you do not stuff garbage into the prompt. Thresholds depend on embedding model and corpus — calibrate on your golden eval set, do not copy a magic number from a blog. If nothing passes threshold, say "I don't know" or offer human transfer — VoXgent did intent-based transfer when confidence was low.

**Follow-up:**

1. **Absolute score or relative rank?**  
   **Say this:** > Use both: top chunks must beat a floor AND beat the gap to rank 10. A high score alone can mislead if everything scores high on a vague query.

---

### Q29. Query rewriting / multi-query.

**Say this:**

> Users speak vaguely — "what about that policy?" Query rewrite uses LLM plus chat history to produce a standalone search query. Multi-query generates several phrasings, retrieves for each, then merges results — better recall, higher cost. VoXgent voice turns were short; rewrite helped before Pinecone search on follow-up questions.

**Compare:**

> **Single query:** fast — enough for first turn FAQ.  
> **Rewrite / multi-query:** better on conversational follow-ups — worth the extra LLM call in support flows.

**Follow-up:**

1. **Where does rewrite run in LangGraph?**  
   **Say this:** > Dedicated node before retrieve. If retrieval scores are weak, loop back to rewrite with a different instruction — max two tries to protect latency.

---

### Q30. What is HyDE?

**Say this:**

> HyDE is Hypothetical Document Embeddings. The LLM writes a fake answer paragraph, you embed that paragraph, and search with it instead of the short user question. Helps when queries are underspecified. Costs extra latency and an LLM call — use selectively, not on every VoXgent voice turn.

**Compare:**

> **Standard embed query:** fast — works for clear questions.  
> **HyDE:** better recall on vague queries — too slow for tight voice SLA unless cached.

**Follow-up:**

1. **HyDE vs query rewrite?**  
   **Say this:** > Rewrite makes a better search question. HyDE embeds a fake document. Both help recall; rewrite is usually cheaper and enough.

---

### Q31. Hybrid search + Reciprocal Rank Fusion (RRF).

**Say this:**

> Hybrid runs dense vector search and sparse keyword search like BM25. Dense catches paraphrases; sparse catches exact IDs and rare tokens. RRF merges ranked lists without needing comparable scores — score equals sum of 1 over rank plus constant. Strong for enterprise docs with SKUs, codes, and natural language mixed. VoXgent used hybrid on clients with heavy jargon in sales and healthcare.

**Compare:**

> **Dense only:** semantic match — misses exact code strings.  
> **Sparse only:** keyword match — misses paraphrases.  
> **Hybrid + RRF:** best of both — slight latency cost.

**Follow-up:**

1. **Where does BM25 live?**  
   **Say this:** > Elasticsearch, OpenSearch, dedicated sparse index, or Pinecone sparse features depending on stack. Same chunk text as dense index — keep doc IDs aligned.

---

### Q32. What is MMR (Maximal Marginal Relevance)?

**Say this:**

> MMR picks chunks that are relevant but not redundant. It balances similarity to the query against similarity to chunks already selected. Stops top-k from being five copies of the same paragraph with slight overlap. Useful after hybrid fusion when overlap-heavy chunking inflates results.

**Compare:**

> **Pure top-k by score:** may duplicate same section.  
> **MMR:** diverse context — better token use in prompt.

**Follow-up:**

1. **MMR vs reranker?**  
   **Say this:** > MMR is cheap diversity heuristic. Reranker is a model that scores query-chunk pairs — slower but smarter. Can use MMR before rerank on large candidate sets.

---

### Q33. Cross-encoder reranking — what and why?

**Say this:**

> Bi-encoder embeddings score query and chunk separately — fast but coarse. Cross-encoder feeds query and chunk together through one model — more accurate, slower. Pattern: retrieve 20 to 50 cheaply with embeddings, rerank to top 3 to 5, then generate. VoXgent used reranking on text-heavy support flows where precision mattered; sometimes skipped on voice when latency was tight.

**Compare:**

> **Bi-encoder retrieve:** milliseconds — scale to millions.  
> **Cross-encoder rerank:** tens to hundreds of ms on tens of docs — production sweet spot before LLM.

**Follow-up:**

1. **Skip rerank when?**  
   **Say this:** > Voice under strict p95 budget, FAQ with high-confidence top-1 score, or cached identical query. Always log when rerank is skipped so you can measure impact.

---

### Q34. Contextual compression / packing.

**Say this:**

> Retrieved chunks may have filler sentences. Compression drops irrelevant sentences inside each chunk or summarizes the retrieved set to fit the token budget while keeping facts. Critical for voice latency and LLM cost. LangChain has contextual compression retriever patterns; we also trimmed by score and hard token cap before prompt on VoXgent.

**Follow-up:**

1. **Compress before or after rerank?**  
   **Say this:** > After rerank — compress the final 3 to 5 winners, not the whole candidate pool. Saves compute and keeps quality.

---

### Q35. Conversation-aware retrieval.

**Say this:**

> Do not embed the raw last user turn alone on turn five — "cancel it" means nothing without history. Rewrite into a standalone query using recent turns. Optionally pull long-term memory from a separate store. Do not dump full chat history into vector search — embed a rewritten query instead. VoXgent passed trimmed history into a rewrite node before Pinecone on multi-turn support calls.

**Compare:**

> **Stateless retrieve:** fine for single FAQ question.  
> **Conversation-aware:** required for voice and chat follow-ups.

**Follow-up:**

1. **How much history in rewrite?**  
   **Say this:** > Last 2 to 4 turns usually enough. More adds noise and tokens. Summarize older turns into memory store if needed.

---

## G. Generation & Prompting for RAG

### Q36. How do you structure a RAG prompt?

**Say this:**

> System block: role, rules, answer only from Context, cite sources, refuse if missing. Context block: numbered chunks with source and page. Chat history: last N turns trimmed. User block: current question. Low temperature for factual tasks. Explicit instruction: if context does not support the answer, say I do not know and offer human handoff. VoXgent healthcare prompts were strict about not inventing medical advice outside context.

**Follow-up:**

1. **Put context before or after instructions?**  
   **Say this:** > System instructions first, then context, then user question — standard pattern. Some teams repeat "use only context" after the chunks to fight lost-in-the-middle.

---

### Q37. Lost-in-the-middle problem.

**Say this:**

> LLMs pay less attention to content in the middle of a long context window. Mitigations: put the most important chunks first and last, reduce k, rerank hard, compress filler, or ask the model to cite chunk IDs so it must read each block. Voice agents keep context short partly for this reason — VoXgent prompts rarely exceeded a few chunks.

**Compare:**

> **Long stuffed context:** middle facts get ignored.  
> **Short reranked context:** model actually uses what you retrieved.

**Follow-up:**

1. **Does reranking help lost-in-the-middle?**  
   **Say this:** > Yes — best chunk at position one matters more than ten mediocre chunks filling the window.

---

### Q38. Citations — how and why?

**Say this:**

> Return doc_id, title, page, or section with the answer. Optionally force the model to reference chunk numbers in the reply. Builds user trust, helps debug wrong answers, and reduces liability in regulated domains. Infosys healthcare clients will ask how you prove the answer came from their policy doc — citations are the proof.

**Follow-up:**

1. **Citation in voice vs text?**  
   **Say this:** > Voice: speak source briefly — "according to your benefits guide section 4." Text: clickable link or footnote. Post-call summary can list full citations in structured JSON.

---

### Q39. What if context contradicts itself?

**Say this:**

> Prefer newest doc_version or latest effective_date via metadata sorting before prompt. Instruct model to flag conflict and not pick randomly. For healthcare, escalate to human when policies disagree. VoXgent prompts told the agent to say two sources disagree and offer transfer rather than guess.

**Follow-up:**

1. **Can reranking fix contradictions?**  
   **Say this:** > Reranking picks relevance, not truth. Fix with metadata — date, version, authority level — and business rules in the graph.

---

## H. Evaluation (interview differentiator)

### Q40. How do you know RAG quality is good?

**Say this:**

> Build a golden Q&A set from real user questions and expected answers or expected source docs. Measure retrieval: recall at k, MRR, nDCG. Measure generation: faithfulness, relevance, correctness. Measure ops: latency p95, cost per query, citation accuracy. Tools like RAGAS help automate scores; voice needs human review of call transcripts too. I learned on VoXgent that retrieval metrics predict answer quality better than vibe-checking prompts alone.

**Follow-up:**

1. **Minimum before production launch?**  
   **Say this:** > 50 to 100 golden questions per domain, recall at k above your bar, faithfulness spot-check, tenant isolation test, and p95 latency on voice path.

---

### Q41. Faithfulness vs answer relevance.

**Say this:**

> Faithfulness means every claim in the answer is supported by retrieved context — no hallucination. Relevance means the answer actually addresses what the user asked. You can be faithful but irrelevant if wrong docs were retrieved. You can sound relevant but unfaithful if the model ignored context and invented details. Eval both separately on VoXgent-style flows.

**Compare:**

> **Faithful + relevant:** goal state.  
> **Faithful + irrelevant:** retrieval problem — fix search and chunking.  
> **Relevant-sounding + unfaithful:** generation problem — tighten prompt, lower temperature, add grounding checks.

**Follow-up:**

1. **Which do you fix first in production?**  
   **Say this:** > Retrieval first. A perfect prompt cannot fix missing chunks.

---

### Q42. Offline vs online evaluation.

**Say this:**

> Offline is curated golden sets before deploy and after every index or model change. Online is production signals: thumbs up/down, groundedness checker on a sample, escalation rate to human, periodic audit of call summaries. Shadow traffic compares new retriever against old without user impact. VoXgent used offline sets for RAG changes and monitored transfer-to-human rate online as a quality signal.

**Compare:**

> **Offline:** controlled, repeatable — gate deploys.  
> **Online:** real user drift — catch what golden sets miss.

**Follow-up:**

1. **RAGAS in production?**  
   **Say this:** > Often offline or sampled online — full RAGAS every query is too costly. Use lightweight faithfulness checks on critical paths.

---

### Q43. Debugging a wrong answer — your checklist.

**Say this:**

> Step one: was the right chunk in the index? Step two: was it retrieved in top-k? Step three: did it survive rerank and land in the prompt? Step four: did prompt rules allow refuse instead of guess? Step five: did the model ignore context anyway? Step six: did a tool overwrite or contradict RAG facts? Fix the earliest failing stage — most VoXgent bugs were retrieval or tenant filter, not the LLM being "dumb."

**Follow-up:**

1. **What do you log to make this fast?**  
   **Say this:** > request_id, chunk IDs, scores, rerank order, prompt token count, model version, and final answer hash — replay one bad call in staging.

---

## I. Production, Latency, Cost, Reliability

### Q44. Latency budget for real-time voice RAG (VoXgent-style).

**Say this:**

> Voice needs tight time-to-first-token. Budget roughly: STT, then embed plus retrieve in parallel where possible, small k, skip rerank if over budget, compress context, stream LLM output to TTS. Cache hot FAQ embeddings and answers in Redis. Use a smaller model for query rewrite, stronger model only for final answer if needed. VoXgent targeted sub-second retrieval and fast LLM start so the caller does not hear long dead air.

**Compare:**

> **Text chat:** can afford rerank and larger k.  
> **Voice (VoXgent):** retrieval and prompt must stay lean — every 200 ms matters on a live call.

**Follow-up:**

1. **Biggest latency win?**  
   **Say this:** > Smaller k, caching normalized queries, and parallel STT finalize with embed prep. Rerank was optional on voice hot path.

---

### Q45. Caching layers.

**Say this:**

> Cache query embeddings for repeated questions. Cache retrieval results for identical normalized queries and same index version. Cache full answers for top FAQs. Cache document embeddings at ingest — never re-embed unchanged chunks. Invalidate on doc_version bump or tenant corpus update. VoXgent Redis cached FAQ retrieval for outbound campaign scripts that repeated often.

**Follow-up:**

1. **Cache key includes what?**  
   **Say this:** > Normalized query text, tenant_id, index version, and filter set. Missing tenant in key causes cross-tenant cache bleed — same severity as filter miss.

---

### Q46. Failure modes and fallbacks.

**Say this:**

> Vector DB timeout — fall back to keyword search or cached FAQ slice. Low retrieval confidence — say I do not know and transfer to human on VoXgent Twilio flows. LLM outage — degraded canned response plus alert. Ingest failure — serve last good index version, flag stale banner internally. Never silent failure — user should get honesty or human, not a confident wrong answer.

**Compare:**

> **Fail closed (healthcare):** no guess — transfer human.  
> **Fail soft (sales FAQ):** cached top answers — with staleness awareness.

**Follow-up:**

1. **Intent-based transfer on VoXgent?**  
   **Say this:** > Yes — low confidence, angry sentiment, or explicit ask for human triggered live transfer via Twilio, not just a text message.

---

### Q47. Prompt injection via retrieved documents.

**Say this:**

> Malicious or compromised docs can say "ignore previous instructions." Treat retrieved text as untrusted data, not system commands. Keep system prompt in a trusted layer the model prioritizes. Sanitize HTML docs, limit tool permissions, never execute code or SQL from retrieved content. Enterprise ingest should scan uploads; ACL on who can index docs.

**Follow-up:**

1. **Can LangGraph help?**  
   **Say this:** > Yes — tool calls go through allowed nodes with validation. Retrieved text never directly triggers CRM write without a structured intent check.

---

### Q48. PII in RAG corpora.

**Say this:**

> Redact or mask PII at ingest when possible — names, phone, SSN patterns. Encrypt at rest, strict ACL metadata, minimize what goes into logs and third-party LLM prompts. Follow client data residency — some Infosys clients cannot send certain fields to US APIs. VoXgent healthcare flows minimized PHI in prompts and relied on metadata filters for sensitive doc classes.

**Follow-up:**

1. **PII in embeddings?**  
   **Say this:** > Embeddings are not reversible plain text but still sensitive — treat stored vectors as confidential, same ACL as source doc.

---

### Q49. Cost knobs.

**Say this:**

> Batch embeddings at ingest. Use smaller embed model if eval passes. Smaller k and compression cut LLM input tokens. Cache FAQ paths. Cheap model for rewrite and routing, expensive model only for final answer. Skip HyDE and multi-query on hot paths. Monitor cost per tenant — sales bot with huge corpus costs more than narrow support FAQ.

**Follow-up:**

1. **Biggest cost surprise in VoXgent?**  
   **Say this:** > Re-embedding entire corpus on model change and unbatched ingest early on — batching and version planning fixed it.

---

### Q50. Observability — what do you log?

**Say this:**

> request_id, tenant_id, query text hashed or redacted, retrieved chunk IDs and scores, rerank order, prompt token counts, model name, latency per stage — embed, retrieve, rerank, LLM — tool calls, transfer flag, user feedback. Essential for Infosys production support and for debugging "why did the bot say that on call 4821?"

**Follow-up:**

1. **OpenTelemetry or custom?**  
   **Say this:** > Either works — span per stage in the RAG path. Dashboard p95 retrieve latency and retrieval-empty rate per tenant.

---

## J. Advanced & Agentic RAG

### Q51. Corrective / Self-RAG ideas (high-level).

**Say this:**

> After first retrieval, a critic step asks: is context enough to answer? If not, rewrite query and search again, or try web search fallback if allowed. Self-RAG adds generation-time checks — does each sentence follow from context? LangGraph conditional edges implement this cleanly: retrieve, grade, branch to rewrite or generate. VoXgent used a light version — retry retrieve once before human transfer.

**Compare:**

> **Single-shot RAG:** one retrieve, one answer — fast.  
> **Corrective RAG:** loop until good enough or max tries — better quality, higher latency.

**Follow-up:**

1. **Max loops on voice?**  
   **Say this:** > One retry max on live call — then answer from best effort or transfer. More loops kill SLA.

---

### Q52. GraphRAG (concept).

**Say this:**

> Build a knowledge graph from docs — entities and relations — plus vector search on text. Retrieve subgraph plus passages for multi-hop questions like "how does policy A affect product B eligibility?" Heavier to build and maintain than flat vector RAG. Useful for compliance and interconnected policies; overkill for simple FAQ. VoXgent stayed vector-first; graph is on my radar for complex healthcare networks.

**Compare:**

> **Vector RAG:** fast to ship — semantic chunk match.  
> **GraphRAG:** better multi-hop reasoning — needs entity extraction pipeline.

**Follow-up:**

1. **GraphRAG vs fine-tune?**  
   **Say this:** > GraphRAG keeps facts updatable in the graph and index. Fine-tune bakes facts into weights — bad for changing policies.

---

### Q53. RAG + tools together (your VoXgent pattern).

**Say this:**

> RAG reads knowledge — policies, scripts, product specs. Tools take actions — update Salesforce, read Google Sheets, send SMS, Canvas EMR lookup. Flow: retrieve facts, classify intent, maybe call tool with validated args, optionally retrieve again with tool output, then respond on voice. LangGraph nodes separated read from write. VoXgent was never RAG-only — sales and support needed CRM and scheduling actions.

**Compare:**

> **RAG-only:** answers from docs — no side effects.  
> **RAG + tools:** answers plus enterprise actions — VoXgent production pattern.

**Follow-up:**

1. **Retrieve before or after tool call?**  
   **Say this:** > Usually before — ground the plan. After tool returns new IDs or dates, second retrieve can pull doc sections referenced by the tool result.

---

### Q54. Multimodal RAG.

**Say this:**

> Index images, scans, or slides via captions or multimodal embeddings. Retrieve text and image references together. Generate with a vision-language model when the answer needs a diagram — e.g. device setup picture in support. VoXgent was mostly voice plus text docs; scanned PDF captions covered most healthcare edge cases without full VLM in the hot path.

**Follow-up:**

1. **Voice agent describing an image?**  
   **Say this:** > Retrieve caption chunk, LLM summarizes spoken steps — no need to send pixels to the caller.

---

### Q55. Streaming and RAG.

**Say this:**

> Retrieval is usually blocking — you need context before safe generation. After context is ready, stream LLM tokens to TTS for faster perceived response. Speculative retrieve on partial STT is advanced — start search on interim transcript, refine when final. VoXgent pipelined STT finalize, retrieve, LLM stream, TTS to hide latency on support calls.

**Compare:**

> **Non-streaming:** wait for full answer — bad on voice.  
> **Stream after retrieve:** user hears speech sooner — VoXgent default.

**Follow-up:**

1. **Stream before retrieval finishes?**  
   **Say this:** > Risky — model may hallucinate before context arrives. Only with speculative retrieve and ability to cancel or revise early tokens.

---

## K. Comparison questions interviewers love

### Q56. RAG vs Fine-tuning vs Long context — decision table.

**Say this:**

> Changing enterprise facts — use RAG. Style, tone, or format — fine-tune or strong prompting. Few small docs temporary — long context paste. Actions on systems of record — tools plus RAG. Lowest hallucination on private data — RAG plus faithfulness checks, not fine-tune alone. VoXgent used RAG for client knowledge and prompting plus tools for behavior — no custom model fine-tune for each client.

**Compare:**

> **RAG:** fresh docs, citations, multi-tenant — VoXgent core.  
> **Fine-tune:** fixed behavior, domain language — expensive per client.  
> **Long context:** simple but costly at scale — not for million-token corpora.

**Follow-up:**

1. **Can you combine RAG and fine-tune?**  
   **Say this:** > Yes — fine-tune for tone and tool-use format, RAG for facts. Facts still come from index at query time.

---

### Q57. LangChain retrievers vs custom retrieval code.

**Say this:**

> LangChain retriever gets you Pinecone, BM25, ensemble hybrid fast — good for integration. Custom code when you need strict tenant filters, custom RRF fusion, detailed stage logging, or tight latency control. Either way you own evaluation — the wrapper does not fix bad chunks. VoXgent used LangChain retriever wrapped with our tenant filter and logging; graph orchestration was LangGraph.

**Compare:**

> **LangChain retriever:** speed of setup — VoXgent RAG wiring.  
> **Custom:** full control — same patterns, your code.

**Follow-up:**

1. **Would Infosys clients care which you use?**  
   **Say this:** > They care about security, latency, and accuracy — not the wrapper. Explain the design; mention LangChain if JD asks.

---

### Q58. "We already have Elasticsearch — do we need a vector DB?"

**Say this:**

> Elasticsearch does BM25 well and now supports dense vectors and hybrid search. If the client already runs ES at scale, start there — less new infra. Dedicated vector DB like Pinecone or Qdrant often wins on pure ANN latency and simple metadata filtering at huge scale. Many enterprises run hybrid ES plus vector DB. Match the client stack — Infosys delivery is about their constraints, not dogma. VoXgent used Pinecone because we had no legacy ES mandate.

**Compare:**

> **Elasticsearch hybrid:** one stack for ops team already on ES.  
> **Vector DB:** optimized ANN and dev experience for RAG-heavy products.

**Follow-up:**

1. **Migration path?**  
   **Say this:** > Dual-write embeddings to ES and Pinecone, compare recall and p95, cut over when vector DB wins on eval — do not big-bang without metrics.

---

## L. Tie-back answers using your experience

### Q59. How did RAG work in VoXgent?

**Say this:**

> I built the RAG layer on VoXgent — documents ingested, chunked, embedded, stored in Pinecone with tenant metadata. LangChain wired retriever and prompt templates. LangGraph ran the live flow: rewrite query if needed, retrieve with filters, optional rerank, inject context, generate answer, or branch to tool call or human transfer on Twilio. Domains were healthcare, sales, and support — each client had their own knowledge base. Tool calling connected Salesforce, Canvas EMR, Google Sheets, SMS — so the agent did more than read docs. Outbound campaigns on GCP Pub/Sub and Cloud Tasks dialed thousands of calls against the same grounded knowledge.

**Compare:**

> **Demo RAG:** retrieve and chat.  
> **VoXgent RAG:** retrieve on live voice, cite sources, call enterprise APIs, transfer human when grounding fails — production grade.

**Follow-up:**

1. **What did you own vs team?**  
   **Say this:** > I owned RAG pipelines, tool-calling orchestration on top of RAG, and several integrations. Three-person backend — schemas and API contracts were shared design.

---

### Q60. Biggest RAG lesson from production.

**Say this:**

> Most "LLM bugs" were retrieval, chunking, tenant filters, or orchestration — not the model being wrong. Measure retrieval first, prompts second. Add LangGraph when you need retries, tool branches, and human handoff — straight chains hide production complexity. One wrong tenant filter is worse than one weak prompt. That mindset came from debugging real VoXgent call failures, not from reading papers.

**Follow-up:**

1. **What would you improve next?**  
   **Say this:** > Formal online eval dashboard — retrieval-empty rate and faithfulness sampled per tenant — and stronger golden sets per healthcare client before each corpus drop.

---

## Quick drill (say answers in <45s each)

1. What is RAG?  
2. Chunking trade-offs  
3. Why same embedding model?  
4. Hybrid + RRF  
5. Reranking  
6. Faithfulness vs relevance  
7. Tenant isolation  
8. Hallucination controls  
9. Voice latency tactics  
10. RAG + tools vs RAG-only  

---

**Next:** `03_Structured_Output_LLM_Integration_Grounding.md` for structured outputs, API integration patterns, and grounding.
