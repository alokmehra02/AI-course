# 04 — AI Pipeline: Chunk → Embed → Search → GraphRAG Q&A

**Focus:** ML/AI depth for RAG interviews — extraction, chunking, embeddings, similarity, hybrid retrieval, reranking, Graph-RAG, and failure modes. Complements architecture (`01`, `02`) and lifecycle Q&A (`03`).

**Audience:** Alok — speakable answers for AI/ML rounds on million-document RAG pipelines.

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask

**VoXgent anchor:** On VoXgent.AI I owned chunking → embedding → Pinecone retrieval with tenant filters, optional hybrid search, and reranking when latency allowed. Graph-RAG was the upgrade path for cross-document reasoning; chunk RAG stayed the default for factual lookup.

---

## Related links

| Topic | Where |
|-------|-------|
| 1M docs architecture | [01 — Design: 1M Documents](./01_Design_1M_Documents_Architecture.md) |
| Cloud vs local, update/delete | [02 — Design: Ingest Lifecycle](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md) |
| System design Q&A (50) | [03 — Q&A: System Design & Lifecycle](./03_QA_System_Design_Ingestion_Lifecycle.md) |
| Embeddings & vector DB deep dive | [Infosys 05 — Embeddings & Retrieval](../Infosys_Interview_Prep/05_Embeddings_VectorDB_Retrieval_QA.md) |
| Embeddings fundamentals | [Artifact L2 — Embeddings](../Artifacts/lesson_2_embeddings.md) |
| Production RAG pipeline | [Artifact L5 — RAG Production](../Artifacts/lesson_5_rag_production_pipeline.md) |
| LLM system design | [SD 14 — AI/LLM System Design](../System_Design_Prep/14_AI_LLM_System_Design.md) |

---

## A. Extraction & Chunking (Q1–Q12)

### Q1. PDF text extraction vs OCR — when do you use each?

**Say this:**

> If the PDF has a **text layer** — born-digital exports, Word-to-PDF — I extract text directly with PyMuPDF, pdfplumber, or Unstructured. That's fast, cheap, and preserves selectable text. If it's a **scan or image-only PDF**, there's no text layer — I run **OCR** (Tesseract, AWS Textract, Google Document AI). OCR is slower, costs more, and introduces character errors that hurt retrieval on part numbers and legal clauses. My rule: detect first — if extracted text is empty or garbage, fall back to OCR; never OCR everything by default.

**Compare:**

> **Direct text extraction:** fast, accurate for digital PDFs, preserves structure hints. **OCR:** necessary for scans, error-prone on tables and small fonts, adds latency and cost.

**Follow-up:**

1. **How do you detect scan vs digital?**  
   **Say this:** Check character count per page after extraction. If a page has images but near-zero text, or text is gibberish, route to OCR. Some libraries expose `is_encrypted` or font metadata — use that as a signal too.

2. **What OCR errors hurt RAG most?**  
   **Say this:** Swapped digits in policy IDs, broken table rows, and merged columns — those create wrong chunks that retrieve confidently but answer incorrectly.

---

### Q2. How do you handle tables in PDFs during extraction?

**Say this:**

> Tables are where naive PDF extraction fails. I prefer tools that output **structured table objects** — Unstructured, Camelot, Tabula, or cloud APIs like Textract — rather than flattening a table into one paragraph. Each table becomes either a **Markdown table string** in the chunk or a **JSON row-per-record** representation with metadata like `table_id` and `page`. I never let a 50-row table become one giant chunk — I split by row groups or summarize the header + sample rows depending on query patterns.

**Compare:**

> **Flatten to prose:** simple but loses column semantics — "Premium $500" detached from "Plan Gold." **Structured table chunk:** preserves column headers in every chunk, better for numeric and comparison questions.

**Follow-up:**

1. **Do you embed tables differently from prose?**  
   **Say this:** Same embedding model, but I prepend the table caption and column headers to every table chunk so the vector captures schema context, not just cell values.

---

### Q3. How do you extract and chunk DOCX vs PDF?

**Say this:**

> **DOCX** is XML under the hood — python-docx or Unstructured gives me headings, lists, and tables with structure intact. I chunk DOCX **header-aware**: each section under an H2 becomes a logical unit. **PDF** loses structure unless I parse layout — headings aren't always tagged. For DOCX I trust the outline; for PDF I infer structure from font size, bold, and whitespace. Same downstream pipeline — chunk → embed → upsert — but extraction quality differs, so I tag `source_format` in metadata for debugging.

**Compare:**

> **DOCX:** rich structure, easier header-aware chunking. **PDF:** universal client format, messier layout, more OCR and table risk.

**Follow-up:**

1. **Which format do you prefer for ingest?**  
   **Say this:** DOCX when clients can provide it — less extraction loss. PDF is the reality for legal and compliance KBs, so the pipeline must handle both.

---

### Q4. How does recursive character text splitting work?

**Say this:**

> **Recursive character text splitter** — LangChain's default pattern — tries to split on a **priority list of separators** before hard-cutting mid-word. Typical order: `\n\n` (paragraphs), `\n` (lines), `. ` (sentences), ` ` (words), then empty string (character-level). It recursively splits the largest pieces first; if a piece still exceeds `chunk_size`, it drops to the next separator. You set `chunk_size` in characters or tokens and `chunk_overlap` so context isn't lost at boundaries. It respects document flow better than blind fixed-size cuts.

**Compare:**

> **Fixed-size splitter:** one cut length — fast but splits mid-sentence. **Recursive splitter:** hierarchy of natural breaks — better coherence, still deterministic and cheap.

**Follow-up:**

1. **What's the default separator list in LangChain?**  
   **Say this:** `["\n\n", "\n", " ", ""]` — paragraph, line, word, character. You can customize — e.g. add `"."` or `"|"` for Markdown tables or log formats.

2. **Characters vs tokens for chunk_size?**  
   **Say this:** Tokens align with embedding model limits; characters are simpler but approximate. For production I measure token count with the same tokenizer the embedder uses when limits are tight.

---

### Q5. Fixed-size chunking — when is it enough?

**Say this:**

> **Fixed-size chunking** splits every N characters or tokens with optional overlap — no separator logic. It's fine for **homogeneous text** — chat logs, plain notes, uniformly formatted articles — where structure doesn't matter. It's the wrong default for policies, manuals, and Markdown with headers. I use fixed-size only as a fallback when recursive or semantic chunking adds no value, or for very high-throughput ingest where simplicity beats quality.

**Compare:**

> **Fixed-size:** O(n) simple, predictable chunk count, bad at boundaries. **Recursive/semantic:** better retrieval quality, slightly more compute at ingest.

**Follow-up:**

1. **Typical fixed size you'd pick?**  
   **Say this:** 512–1024 tokens with 10–20% overlap as a starting point — then tune against a golden question set, not guesswork.

---

### Q6. What is chunk overlap and why does it matter?

**Say this:**

> **Overlap** means consecutive chunks share trailing/leading text — e.g. 512-token chunks with 64-token overlap. Without overlap, a sentence split across two chunks may appear in **neither** chunk fully, so neither embeds the complete thought and retrieval misses both. Overlap duplicates some text in the index — that's intentional storage cost for better recall. I usually set overlap to **10–20% of chunk size**, not 50% — too much overlap bloats the index without proportional gain.

**Compare:**

> **Zero overlap:** smaller index, boundary misses. **Moderate overlap:** standard production tradeoff. **Heavy overlap:** diminishing returns, duplicate hits in top-k.

**Follow-up:**

1. **Does overlap hurt deduplication at query time?**  
   **Say this:** You may get two near-duplicate chunks in top-k — dedupe by `parent_id` or MMR after retrieval fixes that.

---

### Q7. What is semantic chunking and when do you use it?

**Say this:**

> **Semantic chunking** groups sentences or paragraphs by **embedding similarity** — when cosine distance between consecutive units jumps, start a new chunk. The idea: each chunk is one "topic bubble," not an arbitrary character count. It improves retrieval when documents mix unrelated sections in one long page. Cost: you embed many small units at ingest time, so it's slower than recursive splitting. I use it for **long unstructured memos** or when eval shows recursive chunks consistently split mid-topic.

**Compare:**

> **Recursive (rule-based):** fast, deterministic, good default. **Semantic (embedding-based):** better topic coherence, higher ingest cost, needs threshold tuning.

**Follow-up:**

1. **How do you pick the breakpoint threshold?**  
   **Say this:** Plot similarity scores between adjacent sentences on sample docs — look for natural dips. Start around percentile drop or a fixed cosine gap (e.g. 0.2–0.3), then validate recall@k on golden queries.

---

### Q8. Parent-child / small-to-big chunking — explain the pattern.

**Say this:**

> **Small-to-big** (parent-child): index **small chunks** for precise retrieval — 256 tokens — but each small chunk points to a **parent chunk** — 1024 tokens or full section — that you pass to the LLM. Search hits the small, precise needle; generation reads the wider parent for context. In Pinecone I store small-chunk vectors with metadata `parent_id`; after top-k on small chunks, I fetch unique parents from Postgres or a second lookup. This beats one giant chunk for recall and beats tiny chunks alone for answer quality.

**Compare:**

> **Single-size chunks:** simpler ops, compromise on precision or context. **Parent-child:** best of both — slightly more storage and fetch logic.

**Follow-up:**

1. **Do you embed parents too?**  
   **Say this:** Usually only small children are in the vector index. Parents live in object storage or Postgres; optionally embed parents in a separate index for section-level queries.

---

### Q9. Markdown / header-aware chunking — how does it work?

**Say this:**

> For Markdown or HTML, I split on **heading hierarchy** — H1 → H2 → H3 — keeping each section's body with its heading text prepended. A chunk under `## Refund Policy` always starts with that header so the embedding carries section identity. LangChain's `MarkdownHeaderTextSplitter` or custom logic on parsed DOCX/PDF headings does this. Header-aware chunking is my **default for knowledge bases** because users ask section-scoped questions — "What's the refund policy?" — and headers anchor semantics.

**Compare:**

> **Blind recursive split:** may split mid-section, loses "which policy this is." **Header-aware:** chunks align with document outline, better metadata for filters (`section=refund`).

**Follow-up:**

1. **What if headings are missing in PDF?**  
   **Say this:** Infer from font size and bold via layout parsing, or fall back to recursive split with sliding window — and flag low-confidence structure in metadata.

---

### Q10. Why does chunk size matter for embedding models?

**Say this:**

> Embedding models are trained on **text up to a max context length** — often 512 or 8192 tokens depending on model. If your chunk exceeds that, you truncate and **lose tail content** silently. If chunks are too small, each vector lacks context — "It applies after 90 days" means nothing without the subject. Too large, and one vector averages many topics, hurting precision. I match chunk size to **~70–80% of the embedder's max** for long-context models, or **256–512 tokens** for classic 512-limit models like older sentence-transformers.

**Compare:**

> **Tiny chunks (50 tokens):** precise match, weak context. **Huge chunks (4000 tokens):** one topic dilutes vector; retrieval returns whole chapters. **Sweet spot:** one coherent idea per chunk.

**Follow-up:**

1. **Same chunk size for ingest and query?**  
   **Say this:** Queries are short — one embedding. Documents are chunked at ingest; query length doesn't change chunk strategy. Query rewrite may expand the query, not the chunks.

---

### Q11. What metadata do you attach at chunk time?

**Say this:**

> Every chunk gets: `doc_id`, `chunk_id`, `tenant_id`, `source_uri`, `page`, `section_title`, `created_at`, `content_hash`, and `embedding_model_version`. Optional: `language`, `doc_type`, `acl`. Metadata enables **filtered retrieval** — "only this tenant's HR policies" — and **surgical delete** when a PDF updates. I compute `content_hash` so re-ingest skips unchanged chunks and only re-embeds diffs.

**Compare:**

> **Vectors only:** can't filter, can't delete one doc cleanly. **Rich metadata:** mandatory for multi-tenant production and lifecycle events from `02`.

**Follow-up:**

1. **Store metadata in vector DB or Postgres?**  
   **Say this:** Both — Postgres is source of truth; vector DB carries filter fields duplicated for query-time `where` clauses.

---

### Q12. How do you validate chunk quality before embedding?

**Say this:**

> Before bulk embed, I sample: **(1)** chunk length distribution — spikes at max length mean bad splits; **(2)** empty or whitespace-only chunks — drop them; **(3)** golden-doc spot checks — read 20 random chunks aloud, do they make sense standalone? **(4)** duplicate rate — high overlap or re-ingest bugs. Automated: flag chunks under 50 tokens or over model max. Bad chunking can't be fixed at retrieval — garbage in, garbage out.

**Compare:**

> **Skip validation:** fast deploy, silent recall collapse. **Sample + metrics:** cheap insurance before million-doc embed bills.

**Follow-up:**

1. **Metric you'd track post-deploy?**  
   **Say this:** `% chunks retrieved at least once in 30 days` — zero-hit chunks may be orphans or bad splits.

---

## B. Embeddings & Similarity (Q13–Q22)

### Q13. What are embeddings in one sentence?

**Say this:**

> An **embedding** is a fixed-length list of numbers — a vector — that represents text meaning in a high-dimensional space. Similar meanings sit close together; dissimilar ones are far apart. In RAG, I embed every chunk at ingest and embed the user query at search time, then find the closest chunk vectors — that's semantic retrieval.

**Compare:**

> **Keywords (BM25):** match tokens. **Embeddings (dense):** match meaning — "automobile" near "car" even without shared words.

**Follow-up:**

1. **Are embeddings the same as LLM hidden states?**  
   **Say this:** Related idea — embedding models are often smaller encoders trained to produce retrieval-friendly vectors; LLMs can embed too but are heavier. Use purpose-built embedders for scale.

---

### Q14. Must query and document use the same embedding model?

**Say this:**

> **Yes — always the same model and same version** for queries and indexed chunks. Bi-encoders map both into one shared vector space. If you embed docs with `text-embedding-3-large` and queries with `bge-small`, similarity scores are meaningless. Symmetric models use identical API calls for both; some asymmetric models use a `query:` prefix — still one model family, two input formats documented in the model card.

**Compare:**

> **Mixed models:** broken retrieval, looks fine in demos. **Single model/version:** correct geometry in vector space — non-negotiable in production.

**Follow-up:**

1. **What if you upgrade the embedding model?**  
   **Say this:** Full re-embed of all chunks into a new index — blue/green cutover. Never mix versions in one index.

---

### Q15. Cosine similarity — what's the intuition and formula?

**Say this:**

> **Cosine similarity** measures the **angle** between two vectors, not their length. Formula: `cos(θ) = (A · B) / (||A|| × ||B||)` — dot product divided by the product of L2 norms. Range is -1 to 1; for normalized text embeddings typically 0.3–0.9 for related text. If vectors are **L2-normalized** to unit length, cosine similarity **equals the dot product** — faster to compute. I use cosine for semantic text search because magnitude usually isn't meaningful — a longer paragraph shouldn't automatically score higher.

**Compare:**

> **Dot product on unnormalized vectors:** magnitude bias — longer docs win. **Cosine / normalized dot:** direction-only — standard for text.

**Follow-up:**

1. **What score is "good enough" to retrieve?**  
   **Say this:** Don't trust absolute scores across models — calibrate on your golden set. Scores are for ranking within a query; thresholds are domain-specific.

---

### Q16. When do you use a similarity threshold vs pure top-k?

**Say this:**

> **Top-k** always returns k chunks even if all are irrelevant — dangerous for voice bots that must say "I don't know." A **similarity threshold** drops hits below e.g. 0.72 cosine — reduces hallucination from forced context. I use **top-k + threshold together**: retrieve k=20, pass only chunks above threshold to the LLM; if none pass, trigger fallback response. Thresholds need calibration — too high causes false "no answer"; too low lets noise through.

**Compare:**

> **Top-k only:** always grounded-looking, sometimes wrong context. **Threshold + top-k:** honest abstention when nothing matches.

**Follow-up:**

1. **Pitfall with thresholds?**  
   **Say this:** Scores aren't calibrated across queries — one query's 0.75 is another's 0.55. Prefer relative rank + reranker, or percentile within the k-set, not one global magic number without eval.

---

### Q17. Euclidean distance vs cosine — when does each matter?

**Say this:**

> **Euclidean (L2) distance** is straight-line distance in space — sensitive to vector magnitude. **Cosine** ignores magnitude, measures angle. Most text embedding APIs return **normalized vectors**, making cosine and dot product equivalent. Use **cosine** for semantic search unless the model card says otherwise. Euclidean can make sense for unnormalized vectors or certain multimodal spaces — but wrong metric choice silently hurts ranking.

**Compare:**

> **L2 on normalized vectors:** related to cosine but not identical ranking. **Cosine/dot on normalized:** industry default for text RAG.

**Follow-up:**

1. **What metric did Pinecone use on VoXgent?**  
   **Say this:** Cosine — matched our embedder output. Verified normalization once at setup.

---

### Q18. What do embedding dimensions mean (384 vs 1536)?

**Say this:**

> **Dimensions** are the length of the vector — e.g. 384, 768, 1536, 3072. More dimensions can capture finer semantic distinctions but cost more storage, memory, and compute per ANN search. **MTEB leaderboard** models at 768–1024 often match or beat larger dims on quality per dollar. I pick dimensions based on **quality/latency/cost tradeoff**, not "bigger is always better." At million-doc scale, halving dimensions can halve index RAM.

**Compare:**

> **Low dim (384):** fast, cheap, may lose nuance on domain jargon. **High dim (1536+):** richer, heavier index — worth it if eval proves recall gain.

**Follow-up:**

1. **Can you reduce dimensions after embedding?**  
   **Say this:** Matryoshka models support truncating trailing dims with graceful degradation; or train PCA on a sample — but re-evaluate retrieval after any reduction.

---

### Q19. What is MTEB and how do you use it?

**Say this:**

> **MTEB** (Massive Text Embedding Benchmark) is a public leaderboard scoring embedding models on classification, clustering, retrieval, and multilingual tasks. I use it to **shortlist models**, not as gospel — your domain (legal, medical, Hindi-English mix) may differ from benchmark corpora. Process: pick top candidates for retrieval task → run **your golden questions** on your chunks → choose winner on recall@k and nDCG, not MTEB alone.

**Compare:**

> **MTEB-only selection:** fast research, may miss domain fit. **MTEB + internal eval:** production-safe model choice.

**Follow-up:**

1. **Name a strong open reranker/embedder family?**  
   **Say this:** `bge`, `e5`, `gte` for embedders; `bge-reranker`, Cohere rerank for second stage — always validate on your data.

---

### Q20. How do you handle re-embedding when the model changes?

**Say this:**

> Model change = **new vector space**. Steps: (1) freeze writes or dual-write; (2) batch re-embed all chunks with new model; (3) build **new index** (blue); (4) run golden eval comparing old vs new; (5) cut traffic to new index; (6) delete old index. Track `embedding_model_version` on every chunk. Incremental: upsert by `chunk_id` as batches complete — but don't query mixed versions in one index.

**Compare:**

> **In-place update:** impossible without full re-embed. **Blue/green index:** zero-downtime, rollback-friendly.

**Follow-up:**

1. **How long for 1M docs?**  
   **Say this:** Depends on chunk count and API rate limits — parallelize with worker pool, batch API calls (100–500 texts per request), expect hours to days; plan maintenance window or shadow index.

---

### Q21. Embedding batching — best practices at scale?

**Say this:**

> Batch embed at ingest: group **100–500 chunks per API call** within rate limits — far cheaper and faster than one-by-one. Handle **token limits per request** — split batches by total tokens, not just count. Retry with exponential backoff on 429; idempotent upserts by `chunk_id`. Cache embeddings by `content_hash` so unchanged chunks skip re-embed on re-ingest. GPU local models: tune batch size to VRAM — OOM means smaller batches, not serial everything.

**Compare:**

> **Serial embed:** simple, unusable at million scale. **Batched + cached:** standard production throughput.

**Follow-up:**

1. **What if one chunk in a batch fails?**  
   **Say this:** Retry the batch; if persistent, quarantine that chunk in a dead-letter queue — don't block the whole doc ingest.

---

### Q22. Multilingual embeddings — one model or many?

**Say this:**

> For **cross-lingual retrieval** — Hindi query, English doc — use a **multilingual embedding model** (`multilingual-e5`, `text-embedding-3-large` with multilingual support) so all languages share one space. One index, one pipeline. Alternative: translate query to doc language at query time — adds latency and translation errors. For **monolingual per tenant**, language-specific models can win on quality but you multiply indexes. VoXgent-style multi-tenant: one multilingual model + `language` metadata filter when needed.

**Compare:**

> **Multilingual single model:** simpler ops, good for mixed KBs. **Per-language models:** higher quality per language, ops overhead.

**Follow-up:**

1. **Does BM25 work cross-lingually?**  
   **Say this:** Poorly — token mismatch across scripts. Hybrid still helps for SKUs and numbers within same script; cross-lingual needs dense retrieval or translation.

---

## C. Retrieval & Hybrid Search (Q23–Q35)

### Q23. ANN and HNSW — intuition without math overload?

**Say this:**

> Exact nearest-neighbor search over 10M vectors is too slow — O(n) per query. **ANN (Approximate Nearest Neighbor)** trades a little recall for massive speed. **HNSW (Hierarchical Navigable Small World)** builds a multi-layer graph: top layers have long jumps for coarse navigation, bottom layers fine-grained links. Query starts high, greedily walks toward the query vector, then refines — like highway then local streets. Pinecone, Weaviate, pgvector with HNSW — same idea. Tune `ef_search` / `M` for recall vs latency.

**Compare:**

> **Exact (flat):** 100% recall, dies at scale. **HNSW ANN:** ~95–99% recall at ms latency — standard for production RAG.

**Follow-up:**

1. **Can ANN miss the best chunk?**  
   **Say this:** Yes — increase `ef_search` or top-k, add hybrid BM25 as safety net, validate with recall@k on golden set.

---

### Q24. How do you choose top-k?

**Say this:**

> **Top-k** is how many chunks retrieval returns before rerank/generation. Typical: **k=10–20** for LLM context after rerank; retrieve **k=50–100** if a cross-encoder reranker narrows down. Higher k improves recall but adds noise, latency, and token cost. I tune k on golden questions: smallest k where **recall@k** plateaus on the correct chunk. Voice/low-latency: smaller k + good chunking; batch analytics: larger k okay.

**Compare:**

> **Small k (5):** fast, misses multi-hop evidence. **Large k (50+):** better recall, needs rerank or "lost in the middle" hurts LLM.

**Follow-up:**

1. **What is "lost in the middle"?**  
   **Say this:** LLMs overweight start/end of context — critical chunks in position 8–12 get ignored. Rerank to put best chunks first; or use long-context models with caution.

---

### Q25. Score threshold pitfalls in production?

**Say this:**

> Pitfalls: **(1)** treating cosine scores as absolute confidence — they're not calibrated probabilities; **(2)** one global threshold across tenants/domains; **(3)** applying threshold before hybrid fusion when BM25 and dense scores live on different scales; **(4)** threshold on ANN scores after index rebuild — distribution shifts. Fix: calibrate per pipeline version, use **RRF ranks** not raw scores for fusion, combine threshold with **abstain path**, monitor `% queries with zero hits`.

**Compare:**

> **Magic threshold 0.7:** demo-friendly, production-breaking. **Eval-calibrated + abstain:** honest system.

**Follow-up:**

1. **What do you do when zero chunks pass threshold?**  
   **Say this:** Say "I don't have that information," log for content gap analysis, optionally widen k once or trigger web search — never force garbage context.

---

### Q26. What is BM25 and why still use it with embeddings?

**Say this:**

> **BM25** is a sparse keyword ranking function — TF-IDF evolved with length normalization. It excels at **exact tokens**: SKUs, error codes, statute numbers, product IDs. Dense embeddings miss those when the query uses exact jargon not paraphrased in training. **Hybrid retrieval** runs BM25 + dense in parallel — best of semantic paraphrase and lexical precision. On VoXgent, hybrid fixed misses on policy section IDs and part numbers.

**Compare:**

> **Dense only:** great paraphrase, weak exact match. **BM25 only:** great keywords, weak semantic. **Hybrid:** production default for enterprise KBs.

**Follow-up:**

1. **Where does BM25 index live?**  
   **Say this:** Elasticsearch/OpenSearch, Postgres `tsvector`, or vector DBs with sparse support — separate from dense index, fused at query time.

---

### Q27. Hybrid fusion with RRF — explain Reciprocal Rank Fusion.

**Say this:**

> **RRF (Reciprocal Rank Fusion)** merges ranked lists without normalizing incompatible scores. Formula per document: `RRF(d) = Σ 1 / (k + rank_i(d))` across retrievers — typical `k=60`. A doc ranked #1 in BM25 and #3 in dense gets a strong fused score even if raw cosine was 0.42 and BM25 was 12.7. I prefer RRF over weighted linear combo because **score scales differ** — weighted sums need fragile tuning.

**Compare:**

> **Weighted sum of scores:** needs calibration per retriever. **RRF:** rank-only, robust, easy to add a third retriever (e.g. metadata boost).

**Follow-up:**

1. **Can you weight one retriever more in RRF?**  
   **Say this:** Multiply that retriever's term by a constant, or take top-N from one list only — but start unweighted; tune only if eval shows systematic bias.

---

### Q28. Metadata filters — how and when?

**Say this:**

> **Metadata filters** restrict ANN search to a subset — `tenant_id = X AND doc_type = policy AND effective_date <= today`. Apply **before or during** vector search (pre-filtering) depending on DB — Pinecone supports metadata filters on query. Essential for multi-tenant RAG and compliance — never search another client's vectors. Filters that are too narrow cause false empty results — log filter + query pairs.

**Compare:**

> **Post-filter top-k:** retrieve 100, filter to 2 — bad recall. **Pre-filter ANN:** search only valid subset — correct pattern.

**Follow-up:**

1. **Filter on ACL at query time?**  
   **Say this:** Yes — pass user's allowed `doc_ids` or `tenant_id` from auth token into every retrieval call; security fail if retrieval runs unfiltered.

---

### Q29. What is MMR and when do you use it?

**Say this:**

> **MMR (Maximal Marginal Relevance)** reranks candidates to balance **relevance to query** with **diversity among selected chunks**. Score: `λ * sim(query, doc) - (1-λ) * max sim(doc, selected)`. Stops top-k from being ten near-duplicate chunks from the same page. Use when **overlap chunking** or long docs flood results; λ≈0.7 keeps relevance primary. MMR is cheap — no neural model — good pre-step before LLM context assembly.

**Compare:**

> **Pure similarity top-k:** redundant chunks waste context window. **MMR:** diverse evidence, better coverage for multi-aspect questions.

**Follow-up:**

1. **MMR vs cross-encoder rerank?**  
   **Say this:** MMR for diversity among bi-encoder scores; cross-encoder for accurate relevance ordering — can use both: MMR on 50 → cross-encoder top 10.

---

### Q30. Query rewrite — why and how?

**Say this:**

> Voice and chat queries are **short, ambiguous, or coreference-heavy** — "What's the waiting period?" after discussing dental. **Query rewrite** uses an LLM to expand into a standalone search query: "dental insurance waiting period for Plan Gold." Also fix ASR typos. Run rewrite **before embed** — never embed raw "it" and "that." Cache rewrites per session turn. Tradeoff: +200–500ms latency and rewrite hallucination risk — validate rewrite doesn't invent constraints.

**Compare:**

> **Raw query embed:** fast, misses context and pronouns. **LLM rewrite:** better recall, costs latency — mandatory for conversational RAG.

**Follow-up:**

1. **Rewrite with same LLM as generation?**  
   **Say this:** Can use smaller/faster model for rewrite — quality bar is lower than final answer; keep generation model for synthesis.

---

### Q31. HyDE — Hypothetical Document Embeddings?

**Say this:**

> **HyDE** asks the LLM to write a **hypothetical answer paragraph** to the question, then embeds **that fake doc** instead of the query for retrieval. Hypothesis matches document style in vector space — helps when queries are short vs long policy prose. Risks: hypothetical may hallucinate wrong terms and retrieve wrong chunks. I use HyDE selectively when rewrite alone under-retrieves; always A/B on golden set.

**Compare:**

> **Embed query directly:** honest, can mismatch doc/query length style. **HyDE:** better style match, hallucination risk — not default for regulated domains.

**Follow-up:**

1. **HyDE vs multi-query?**  
   **Say this:** HyDE = one synthetic doc; multi-query = several real search queries — multi-query is safer in compliance; HyDE when doc style is very formal and queries are telegraphic.

---

### Q32. Multi-query retrieval — how does it work?

**Say this:**

> **Multi-query:** LLM generates 3–5 diverse search queries from the user question, embed each, retrieve top-k per query, **union + dedupe** chunks, optionally RRF merge. Captures different phrasings — "refund policy," "money back guarantee," "cancellation reimbursement." Better recall for complex questions than single rewrite. Cost: N× retrieval latency — parallelize embed + search calls.

**Compare:**

> **Single query:** fast, one angle. **Multi-query:** higher recall, more index load — good for hard questions offline or premium tier.

**Follow-up:**

1. **Cap queries at how many?**  
   **Say this:** 3–5 — diminishing returns; merge with RRF and dedupe by `chunk_id`.

---

### Q33. Conversation-aware retrieval — what changes?

**Say this:**

> Multi-turn chat requires **session context in retrieval** — not just the last utterance. Patterns: (1) **query rewrite** with last N turns; (2) maintain **conversation summary** embedded alongside query; (3) store `session_id` and boost recently cited chunks. Never retrieve on "yes" or "tell me more" without rewrite. LangGraph: retrieval node reads state `messages` → rewrite → embed → filter by tenant.

**Compare:**

> **Stateless retrieval:** broken follow-ups. **Rewrite + session metadata:** conversational RAG that feels coherent.

**Follow-up:**

1. **Do you embed conversation history into the index?**  
   **Say this:** No — index is document chunks only. History affects **query formulation**, not stored vectors.

---

### Q34. How do dense and sparse scores differ in hybrid pipelines?

**Say this:**

> **Dense cosine** typically 0.2–0.9 for text — higher means closer angle. **BM25** unbounded positive scores — 5 vs 15 isn't intuitive. You **cannot add them directly** without normalization. Use **RRF on ranks** or min-max normalize per query on each list before weighted sum. Log both rank lists during debug — raw score comparison misleads interviewers and engineers.

**Compare:**

> **Raw score fusion:** fragile tuning. **RRF rank fusion:** scale-free, production-standard.

**Follow-up:**

1. **Does Pinecone hybrid return one score?**  
   **Say this:** Depends on product — some return fused rank; you may still run your own RRF across external BM25 + Pinecone dense.

---

### Q35. How do you debug bad retrieval in production?

**Say this:**

> Log per query: rewritten query, top-20 `chunk_id`s with dense/BM25/RRF scores, filters applied, latency. Offline: **recall@k** on golden set weekly. Compare before/after embed model, chunk strategy, or index deploy. Sample failures into human review — "correct chunk in index?" vs "never retrieved?" vs "retrieved but LLM ignored." First check filters and tenant_id bugs — they cause silent empty sets more often than ANN math.

**Compare:**

> **No retrieval logs:** blind debugging. **Structured retrieval trace:** find split between chunking, embed, search, rerank, generate.

**Follow-up:**

1. **Tool you'd use for eval?**  
   **Say this:** Ragas, custom scripts with golden Q&A, or LangSmith traces — measure recall@k, MRR, and faithfulness separately.

---

## D. Reranking (Q36–Q40)

### Q36. Bi-encoder vs cross-encoder for reranking?

**Say this:**

> **Bi-encoder** embeds query and doc separately — dot product score. Fast: millions of candidates. **Cross-encoder** concatenates query+doc through one transformer — attention crosses both; much more accurate relevance judgment. Too slow to score full index — use bi-encoder for **retrieval top-100**, cross-encoder to **rerank top-20 → top-5** for LLM. That's the standard two-stage pipeline.

**Compare:**

> **Bi-encoder only:** ms search, good recall, weaker ordering. **Cross-encoder rerank:** +100–300ms on 20 pairs, much better precision@5.

**Follow-up:**

1. **Can you use cross-encoder for first-stage search?**  
   **Say this:** Only on tiny corpora — O(n) per query. At million docs, always bi-encoder ANN first.

---

### Q37. When is a cross-encoder reranker worth the latency?

**Say this:**

> Worth it when: **(1)** bi-encoder gets correct chunk in top-20 but wrong order; **(2)** questions need fine-grained distinction — similar policy clauses; **(3)** latency budget allows +200ms — async chat yes, sub-second voice maybe not. Skip rerank when failures are **chunking/recall** problems — rerank can't fix missing chunks. Measure precision@5 with/without rerank on golden set.

**Compare:**

> **No rerank:** simpler, faster, good enough for FAQ. **Cross-encoder:** premium accuracy tier or batch Q&A.

**Follow-up:**

1. **How many docs to rerank?**  
   **Say this:** 15–50 candidates — sweet spot; reranking 200 yields diminishing returns vs latency.

---

### Q38. Latency tradeoff of reranking at scale?

**Say this:**

> Cross-encoder cost scales with **pairs × sequence length**. BGE-reranker on 20 chunks × 512 tokens each ≈ 100–400ms on GPU, slower on CPU. Mitigations: rerank fewer candidates, truncate chunk text to relevant span, use **distilled rerankers**, batch pairs on GPU, async rerank for non-voice. Voice path: skip rerank, invest in hybrid + chunking; web chat: rerank default.

**Compare:**

> **Always rerank 100:** accuracy win, latency loss. **Tiered:** rerank only high-stakes or low-confidence retrievals — confidence from top-1 vs top-2 score gap.

**Follow-up:**

1. **Rerank before or after MMR?**  
   **Say this:** Retrieve → MMR diversify 50 → cross-encoder top 10 — order matters less than not reranking duplicates twice.

---

### Q39. Cohere rerank / bge-reranker style — how do they fit?

**Say this:**

> **Cohere Rerank API** and open **bge-reranker-v2-m3** are cross-encoders exposed as API or local model. Input: query + list of doc strings; output: relevance scores sorted. Drop-in after Pinecone retrieval — no re-embedding needed. Cohere: managed, multilingual, pay per search. BGE: self-host on GPU, data residency. Same interface pattern: `rerank(query, documents, top_n=5)`.

**Compare:**

> **API rerank (Cohere):** fast to integrate, ongoing cost. **Self-host bge:** infra burden, no per-call fee, good for high volume.

**Follow-up:**

1. **Same vendor for embed and rerank?**  
   **Say this:** Not required — rerank reads raw text, not vectors. Mix OpenAI embed + Cohere rerank freely.

---

### Q40. Fallback if reranker is down?

**Say this:**

> **Circuit breaker:** if rerank API times out or 503, fall back to **RRF/hybrid order** from bi-encoder + BM25 — don't fail the user request. Log degradation event; alert on-call. Pre-compute: ensure top-k without rerank is "good enough" via eval — rerank is enhancement, not sole quality gate. Optional: lightweight **score boost** by metadata recency while reranker recovers.

**Compare:**

> **Hard dependency on rerank:** outage = total failure. **Graceful degradation:** slightly worse ranking, still answers.

**Follow-up:**

1. **Cache rerank results?**  
   **Say this:** Only for identical query+chunk set — rare in chat; skip cache; cache embeddings and retrieval instead.

---

## E. Graph-RAG & Entities (Q41–Q46)

### Q41. What is Graph-RAG in plain terms?

**Say this:**

> **Graph-RAG** builds a **knowledge graph** from documents — **entities** (people, products, policies) and **relationships** (covers, excludes, reports_to) — then retrieves via graph traversal and **community summaries**, not just flat chunks. Microsoft GraphRAG pattern: extract graph → detect communities → LLM-summarize each community → at query time route to relevant communities and entities, then generate. Beats chunk RAG on **global questions** — "What are the main themes across all HR policies?" — where no single chunk holds the answer.

**Compare:**

> **Chunk RAG:** local evidence, great for factual lookup. **Graph-RAG:** global synthesis, cross-doc reasoning, higher build cost.

**Follow-up:**

1. **Did VoXgent use Graph-RAG in production?**  
   **Say this:** Chunk RAG + Pinecone was production default; Graph-RAG was the path for cross-document analytics and executive summaries — heavier offline pipeline.

---

### Q42. Entity and relation extraction — how?

**Say this:**

> Pipeline: chunk text → **NER + relation extraction** via LLM structured output or dedicated models — "Plan Gold **covers** dental," "Section 4.2 **references** Appendix B." Store `(head, relation, tail)` triples in a graph DB (Neo4j) or adjacency tables. Dedupe entities ("Plan Gold" = "Gold Plan") with embedding clustering or canonical IDs. Quality depends on extraction prompts and human review samples — garbage triples poison traversal.

**Compare:**

> **LLM extraction:** flexible, costly, needs validation. **Rule/regex:** cheap for fixed schemas — policy IDs, dates.

**Follow-up:**

1. **How do you handle extraction errors?**  
   **Say this:** Confidence scores, human-in-loop on sample, periodic graph validation queries — orphan nodes, impossible relations.

---

### Q43. What are community summaries in Graph-RAG?

**Say this:**

> After building the entity graph, run **community detection** (Leiden/Louvain) to find densely connected clusters — e.g. all entities about "refund workflow." An LLM writes a **summary per community** — stored as retrievable text units. Global query "Summarize refund rules company-wide" retrieves relevant **community summaries** first, then drills into entity neighbors and source chunks. Summaries are precomputed — query-time cost is retrieval + one generation, not reading 10,000 chunks.

**Compare:**

> **Chunk-only global query:** retrieve random fragments, LLM hallucinates glue. **Community summaries:** structured map-reduce offline, better global answers.

**Follow-up:**

1. **How often rebuild communities?**  
   **Say this:** On bulk ingest or scheduled batch — not per query. Incremental community update is research-hard; full rebuild on doc set change is simpler.

---

### Q44. When does Graph-RAG beat chunk RAG?

**Say this:**

> Graph-RAG wins on: **(1)** holistic / thematic questions across many docs; **(2)** multi-hop reasoning — "Which products covered by Plan X are also excluded in Region Y?"; **(3)** explorable entity-centric UX — "show everything linked to this vendor." Chunk RAG wins on: **(1)** single-fact lookup; **(2)** low latency MVP; **(3)** strict citation to verbatim policy text; **(4)** smaller corpora where brute chunk search suffices.

**Compare:**

> **Graph-RAG:** higher offline cost, better global intelligence. **Chunk RAG:** simpler, faster to ship, better verbatim QA.

**Follow-up:**

1. **Hybrid approach?**  
   **Say this:** Yes — route query classifier: factual → chunk RAG; global/multi-hop → Graph-RAG path. Best production pattern long-term.

---

### Q45. When does Graph-RAG fail?

**Say this:**

> Failures: **(1)** bad entity extraction → wrong graph → confident wrong paths; **(2)** stale community summaries after doc update; **(3)** over-merge communities — unrelated topics in one summary; **(4)** cost/complexity — 10× ingest time vs chunk-only; **(5)** questions needing **exact verbatim text** — graph abstracts away wording; **(6)** sparse graphs — few entities, no community structure, no gain over chunks.

**Compare:**

> **Force Graph-RAG everywhere:** over-engineering. **Right tool for query type:** chunk for lookup, graph for synthesis.

**Follow-up:**

1. **How detect graph is not helping?**  
   **Say this:** A/B global questions — if Graph-RAG loses to multi-query chunk RAG on faithfulness, simplify or fix extraction.

---

### Q46. PDF updates — how do you invalidate and rebuild the entity graph?

**Say this:**

> Treat graph like derived index — **Postgres/source of truth** for docs. On PDF replace/delete: **(1)** delete all entities/edges sourced from that `doc_id` (track provenance on every triple); **(2)** **invalidate affected community summaries** — any community touching removed entities; **(3)** re-extract from new PDF version; **(4)** merge/dedupe entities — same `entity_id` if canonical match; **(5)** **re-run community detection + re-summarize** changed communities only if incremental tooling exists, else rebuild graph partition for tenant. Same event bus as vector chunk delete in `02`.

**Compare:**

> **Patch one node manually:** error-prone. **Event-driven full re-extract per doc:** consistent, automatable.

**Follow-up:**

1. **Vector index and graph in sync?**  
   **Say this:** Same lifecycle event deletes chunks and graph triples — dual derived indexes from one source-of-truth event; never update one without the other.

---

## F. Failure Modes & Summarization (Q47–Q50)

### Q47. Why does RAG fail at document-level summarization?

**Say this:**

> **Document-level summary** — "Summarize this 80-page policy" — needs **global understanding**, not top-5 chunks. RAG retrieves a biased sample — intro, repeated keywords, random middle — and the LLM **fills gaps with hallucination**. Chunks don't cover all themes evenly; overlap and embedding bias toward query-like sections. Fix: **map-reduce** — summarize each section, then summarize summaries; or **Graph-RAG community summaries**; or full-doc pass with long-context model if it fits. Don't pretend top-k chunk RAG equals summarization.

**Compare:**

> **Top-k RAG "summarize":** incomplete, hallucinated narrative. **Map-reduce / Graph-RAG / long-context:** appropriate architectures.

**Follow-up:**

1. **Can higher k fix it?**  
   **Say this:** k=50 still misses pages and blows context window — doesn't scale linearly to full doc coverage.

---

### Q48. Why do answers go wrong after a PDF update?

**Say this:**

> **Stale derived data** — vector chunks, BM25 index, Graph-RAG summaries, and cached section summaries still reflect the **old PDF** if delete/re-ingest failed partially. User asks about new clause; retriever returns **old chunk** with high similarity; LLM answers confidently from outdated text. Also: **parent-child** stale parents, **entity graph** still links deleted relations, **embedding model version** mixed after partial re-embed. Fix: event-driven delete-by-`doc_id`, verify zero chunks remain, re-ingest, bump `doc_version`, run golden eval on changed sections.

**Compare:**

> **Upsert-only without delete:** classic stale RAG bug. **Delete-then-insert + version metadata:** lifecycle from `02`.

**Follow-up:**

1. **How prove staleness in debug?**  
   **Say this:** Compare retrieved chunk `content_hash` and `doc_version` against Postgres source — mismatch means stale index.

---

### Q49. Silent wrong retrieval — what is it and how to prevent?

**Say this:**

> **Silent wrong retrieval:** system returns an answer with no error, but the **wrong chunks** scored highest — user trusts a false response. Causes: ambiguous query, bad chunk boundaries, hybrid weighting wrong, threshold too low, ANN approximation miss, or stale index. Prevention: **rerank**, **confidence/abstain** when top scores are flat, **cite sources** so user can verify, **faithfulness eval** (Ragas), monitor **user thumbs-down correlated with chunk_ids**, require minimum score gap between rank-1 and rank-2.

**Compare:**

> **Always answer mode:** high hallucination risk. **Abstain + citations + eval:** failures visible, not silent.

**Follow-up:**

1. **Flat score distribution signal?**  
   **Say this:** If top-5 cosine scores within 0.02 — retrieval uncertain — widen with multi-query or ask clarifying question.

---

### Q50. Eval metrics — recall@k, faithfulness, and what else?

**Say this:**

> **Recall@k:** is the gold relevant chunk in top-k retrieved? — measures retrieval quality. **MRR / nDCG:** rank-aware retrieval quality. **Faithfulness (groundedness):** does the answer stick to retrieved text — Ragas `faithfulness` metric. **Answer correctness:** matches gold answer with LLM-judge or exact match. **Citation accuracy:** cited chunk supports the claim. Separate **retrieval vs generation** failures — low recall@k is chunk/embed/search; high recall but wrong answer is LLM or context assembly. Track all on golden set after every pipeline change.

**Compare:**

> **End-to-end accuracy only:** can't localize bug. **Recall@k + faithfulness:** pin retrieval vs generation separately.

**Follow-up:**

1. **Minimum bar before production?**  
   **Say this:** Define SLO on golden set — e.g. recall@10 > 90%, faithfulness > 95% — and regression test on CI for chunk/embedding changes.

2. **How often re-run eval?**  
   **Say this:** Every embed model, chunk strategy, or index config change; weekly smoke on production sample queries.

---

**Next:** [03 — System Design & Lifecycle Q&A](./03_QA_System_Design_Ingestion_Lifecycle.md) · [01 — 1M Architecture](./01_Design_1M_Documents_Architecture.md)
