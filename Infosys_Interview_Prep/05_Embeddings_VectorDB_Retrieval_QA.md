# 05 — Embeddings, Vector DB & Retrieval Mechanics Q&A

**Focus:** The math and systems behind RAG retrieval — embeddings, similarity, ANN indexes, hybrid search, Pinecone ops. Complements `02_RAG_Deep_Dive_QA.md` and `06_RAG_Pipeline_Step_by_Step.md`.

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask

**VoXgent anchor:** On VoXgent.AI I embedded knowledge chunks into Pinecone with tenant metadata, retrieved after conversational query rewrite, and passed grounded context into the voice LLM. Tool actions (CRM, scheduling, human transfer) never went through the vector DB — only knowledge lookup did.

---

## A. Embeddings

### Q1. Sparse vs dense representations?

**Say this:**

> **Sparse** vectors — like BM25 or TF-IDF — are huge but mostly zeros. They match exact keywords well. **Dense** embeddings are a few hundred or thousand numbers that capture meaning — so "car" sits near "automobile." On VoXgent we used dense embeddings in Pinecone for semantic search, and added sparse/BM25-style keyword search when clients had part numbers or policy section IDs.

**Compare:**

> **Sparse:** great for exact tokens, cheap, no GPU for search. **Dense:** great for paraphrases and natural voice questions. **Production RAG:** often both — hybrid beats either alone for enterprise KBs.

**Follow-up:**

1. **Why not just keywords?**  
   **Say this:** Voice users don't say the exact words in the PDF. Dense search catches "waiting period for dental" even if the doc says "benefit commencement timeline."

2. **Did VoXgent use hybrid from day one?**  
   **Say this:** We started dense-only in Pinecone. Hybrid came when we saw misses on error codes, SKU numbers, and legal clause IDs — exact-token queries dense alone handles poorly.

---

### Q2. Why not one-hot encoding for search?

**Say this:**

> One-hot gives each word its own dimension with a 1 or 0. "Car" and "automobile" look completely unrelated — no similarity score. Dimensions explode with vocabulary size, and paraphrases never match. Dense embeddings fix this by putting similar meanings close together in vector space.

**Compare:**

> **One-hot:** no semantic similarity, unusable at scale. **Dense embeddings:** similarity is just distance between vectors — that's what makes RAG retrieval work.

**Follow-up:**

1. **So embeddings replace keywords entirely?**  
   **Say this:** No — they complement keywords. That's why we kept hybrid search for VoXgent clients with structured IDs and compliance text.

---

### Q3. Bi-encoder vs cross-encoder?

**Say this:**

> A **bi-encoder** embeds the query and each document **separately**, then compares vectors — fast enough to search millions of chunks in Pinecone. A **cross-encoder** reads query and document **together** in one model — much more accurate, but too slow for the whole index. Production pattern: bi-encoder for top-k retrieval, cross-encoder to rerank only those top results.

**Compare:**

> **Bi-encoder:** fast ANN search — VoXgent's Pinecone retrieval step. **Cross-encoder:** slow, accurate rerank — optional second stage on top-20 only. Never cross-encode the full KB.

**Follow-up:**

1. **Did VoXgent use a cross-encoder reranker?**  
   **Say this:** We could add one when latency budget allowed — voice is tight, so we prioritized better chunking and hybrid search first. Rerank is the next lever when top-k is good but order is wrong.

2. **What embedding API did you use?**  
   **Say this:** A general-purpose text embedding model via API — same model for indexing and query time. The rule is: never mix models in one Pinecone index.

---

### Q4. Asymmetric retrieval (query vs document encoders)?

**Say this:**

> Some systems train **separate encoders** — one tuned for short queries, one for long documents. Most API models — OpenAI, Cohere, etc. — are **symmetric**: one model for both. On VoXgent we used the **same model** for ingest and query unless the model card explicitly says to prefix queries differently.

**Compare:**

> **Asymmetric (dedicated query/doc models):** can boost recall for short voice utterances vs long PDF chunks. **Symmetric (single model):** simpler ops — one pipeline, one index, fewer bugs.

**Follow-up:**

1. **When would you switch to asymmetric?**  
   **Say this:** When eval shows queries consistently under-retrieve long policy docs even after rewrite and chunking fixes. Otherwise symmetric is fine for MVP and production.

---

### Q5. Normalization of vectors?

**Say this:**

> **Normalization** scales each vector to unit length — length equals 1. After that, **cosine similarity equals dot product**, which is cheaper to compute. Many embedding APIs already return normalized vectors. Before picking a metric in Pinecone, I confirm whether vectors are normalized — wrong metric choice hurts ranking silently.

**Compare:**

> **Normalized + cosine/dot:** standard for semantic text search. **Unnormalized + L2:** magnitude affects distance — usually wrong for text embeddings unless you have a reason.

**Follow-up:**

1. **What metric did Pinecone use on VoXgent?**  
   **Say this:** Cosine — matched our embedding model output. I verified normalization once during setup and didn't change it without re-embedding everything.

---

### Q6. Embedding drift / model upgrades?

**Say this:**

> If you swap embedding models, **old and new vectors live in different spaces** — comparing them is meaningless. Upgrade means: **re-embed all chunks**, rebuild the Pinecone index, evaluate, then cut over. Never mix two model versions in one index. We used a blue/green pattern — new index live, old index deleted after validation.

**Compare:**

> **In-place patch:** impossible without full re-embed. **Blue/green index:** zero-downtime cutover — VoXgent-style production approach.

**Follow-up:**

1. **How do you detect drift in production?**  
   **Say this:** Track retrieval hit rate, nDCG on a golden question set, and user escalation rate. A sudden drop after a deploy often means wrong model, failed ingest, or index pointing at stale namespace.

2. **Can you re-embed incrementally?**  
   **Say this:** Yes — upsert new vectors with stable chunk IDs. But every chunk in that index must use the same model version until full migration completes.

---

### Q7. Multilingual embeddings?

**Say this:**

> If queries and documents span languages — Hindi voice query, English policy PDF — you need a **multilingual embedding model**. A English-only model puts cross-language pairs far apart in vector space, so retrieval fails silently. Pick the model based on client locales before indexing.

**Compare:**

> **Monolingual model:** fine when KB and users are one language. **Multilingual model:** required for mixed-language enterprise clients — common in India deployments.

**Follow-up:**

1. **Did VoXgent need multilingual?**  
   **Say this:** Depends on client — healthcare and support KBs were mostly English, but voice can be code-mixed. We matched embedding model to the client's primary doc language and tested cross-language queries in eval.

---

### Q8. Instruction-tuned embedding models?

**Say this:**

> Some embedding models expect **prefixes** — like `query: ...` for search text and `passage: ...` for documents. If you skip prefixes, recall drops for no obvious reason. Always read the model card and use the same prefixes at ingest and query time.

**Compare:**

> **General embeddings:** same string in, vector out. **Instruction-tuned (E5, BGE-style):** prefixes tell the model whether you're searching or storing — better recall when used correctly.

**Follow-up:**

1. **Where would that bite you on VoXgent?**  
   **Say this:** Ingest pipeline embeds raw chunk text, but query path forgets the `query:` prefix — retrieval looks fine in tests but fails on paraphrases in production. Fix: one shared embedding helper used by both paths.

---

### Q9. Chunk embedding vs document embedding?

**Say this:**

> **Document-level** embedding = one vector for the whole file — good for coarse "which doc is relevant" but bad for precise facts buried on page 40. **Chunk-level** = one vector per section — RAG almost always uses this so the LLM gets the exact paragraph. On VoXgent every Pinecone vector was a chunk, with metadata pointing back to parent doc, page, and section.

**Compare:**

> **Doc embedding:** fast index, low precision. **Chunk embedding:** more vectors, higher precision — standard for voice Q&A where users ask about specific clauses or benefits.

**Follow-up:**

1. **Parent-child indexing?**  
   **Say this:** Retrieve small child chunks for precision, fetch parent section for generation context when the answer needs surrounding paragraphs — useful for long policy docs.

2. **How many vectors per client on VoXgent?**  
   **Say this:** Roughly one per chunk — thousands to tens of thousands per tenant depending on KB size. Capacity planning uses chunk count × dimensions × 4 bytes plus index overhead.

---

### Q10. Can you embed images/audio?

**Say this:**

> Yes. **Multimodal encoders** — CLIP-style — put images and text in the same vector space. For VoXgent-style voice agents the practical path is: **OCR + caption the image**, embed the text, store image URI in metadata. Plain PDF text extraction alone misses answers that live only in a chart or diagram.

**Compare:**

> **Multimodal embedding:** one index for image and text — heavier infra. **Caption-then-embed:** simpler, works with existing text pipeline and Pinecone setup.

**Follow-up:**

1. **What goes in Pinecone metadata for images?**  
   **Say this:** `doc_id`, `chunk_id`, `modality: image`, `source_uri`, `page`, `tenant_id` — same isolation rules as text chunks.

---

## B. Similarity & Ranking

### Q11. Write cosine similarity formula (interview favorite)?

**Say this:**

> Cosine similarity is the dot product divided by the product of the lengths: **cos(θ) = (A · B) / (||A|| × ||B||)**. It measures the angle between two vectors — how aligned their directions are, not how big they are. For normalized text embeddings the range is often 0 to 1 in practice. In Pinecone, higher cosine score = more semantically similar chunk.

**Compare:**

> **Cosine:** direction similarity — standard for normalized embeddings. **Dot product:** same as cosine when vectors are unit length — slightly faster. **L2 distance:** geometric distance — sensitive to magnitude if not normalized.

**Follow-up:**

1. **What's a good similarity threshold?**  
   **Say this:** There's no universal cutoff — it depends on model and domain. I tune on a labeled eval set: pick k and optionally a minimum score below which we refuse or retry rewrite.

---

### Q12. Why not Euclidean (L2) always?

**Say this:**

> **L2 (Euclidean) distance** measures straight-line distance in space. If vectors differ in **magnitude**, L2 can rank wrong — a longer vector looks farther even when direction matches. Semantic similarity for text is about **direction** (meaning), not length. That's why normalized vectors + cosine/dot are preferred for Pinecone text search.

**Compare:**

> **L2:** fine for raw feature vectors where magnitude matters. **Cosine:** fine for normalized semantic embeddings — VoXgent/Pinecone default for text RAG.

**Follow-up:**

1. **When would L2 be OK?**  
   **Say this:** If the provider docs say vectors aren't normalized and recommend Euclidean — but then I'd verify with eval, not assume.

---

### Q13. ANN recall vs latency trade-off?

**Say this:**

> Pinecone and other vector DBs use **approximate nearest neighbor (ANN)** indexes — HNSW-style — to avoid comparing the query to every vector. You tune parameters like **`ef`** or **`probes`** / candidate count: **higher = better recall** (find the true top-k) but **slower and costlier**. Measure **Recall@k** on a fixed eval set before chasing latency.

**Compare:**

> **Exact search:** perfect recall, unusable at millions of vectors. **ANN:** fast, tunable recall — production default for VoXgent-scale KBs.

**Follow-up:**

1. **What if recall is low but latency is fine?**  
   **Say this:** Increase ANN search breadth, increase k slightly, improve chunking/hybrid — don't jump to a bigger model first. Diagnose retrieval before prompt tuning.

2. **Voice latency budget?**  
   **Say this:** Every millisecond counts on a live call — we kept k modest (e.g. 5–10), avoided heavy rerankers in the hot path, and cached embeddings for repeated FAQ queries where possible.

---

### Q14. Reciprocal Rank Fusion formula (conceptual)?

**Say this:**

> **RRF** merges ranked lists from different retrievers without normalizing their scores. For each document: **score += 1 / (k + rank)** — rank 1 gets the biggest bump. Sum scores across dense (Pinecone) and sparse (BM25) lists, then sort. Constant **k** — often 60 — stops the top result from dominating too harshly.

**Compare:**

> **Score blending:** needs calibrated scores across systems — hard. **RRF:** rank-only, simple, works well for **dense + BM25 hybrid** — what we used conceptually on VoXgent when keyword and vector lists disagreed.

**Follow-up:**

1. **Why not average Pinecone score and BM25 score?**  
   **Say this:** Scales differ — cosine 0.82 vs BM25 14.3 means nothing averaged. RRF only cares about position in each list.

---

### Q15. Why top-k then rerank?

**Say this:**

> Cross-encoding **every** chunk in Pinecone is impossible — millions of pairs, seconds per pair. **ANN narrows to top-k** in milliseconds. A **cross-encoder reranker** then re-scores only those 20–50 candidates for better order. Retrieval casts a wide net; rerank polishes the short list before the LLM sees context.

**Compare:**

> **Retrieve only:** fast, good enough when chunking and hybrid are solid — VoXgent default. **Retrieve + rerank:** better order, extra latency — worth it when eval shows right chunks in top-50 but wrong top-5.

**Follow-up:**

1. **What k did VoXgent use?**  
   **Say this:** Small k for voice latency — enough chunks to cover the answer after dedupe, not so many that prompt blows token budget or adds noise (lost-in-middle).

---

## C. Vector Databases & Pinecone

### Q16. What does a vector DB provide beyond a numpy matrix?

**Say this:**

> A numpy matrix in memory is fine for a demo. Production needs **durable storage**, **ANN indexes** for fast search at scale, **metadata filtering** (tenant, domain), **upserts and deletes**, **namespaces**, replication, and an SLA. Pinecone gave us managed ANN + filters so the VoXgent backend didn't operate its own HNSW cluster.

**Compare:**

> **numpy + brute force:** OK for &lt;10k vectors in a notebook. **Pinecone / pgvector / Weaviate:** production retrieval with ops you don't want to own — VoXgent chose Pinecone for managed scale and simple metadata filters.

**Follow-up:**

1. **Why not pgvector in Postgres?**  
   **Say this:** pgvector works when you're already in Postgres and scale is moderate. Pinecone made sense for separate KB scale, ANN tuning, and clear tenant namespaces without loading vectors into app memory.

2. **What would make you pick pgvector?**  
   **Say this:** Strong transactional needs — vectors and business data in one DB — or strict data residency with self-hosted Postgres.

---

### Q17. Metadata filtering performance?

**Say this:**

> Pinecone lets you **filter by metadata** — `tenant_id`, `domain`, `doc_type` — before or during ANN search. Always filter **`tenant_id` first** for multi-tenant isolation. Bad filter design — huge unindexed cardinality — slows queries. High-cardinality filters need planning; low-cardinality enums like tenant and product line work well.

**Compare:**

> **Post-filter in app:** retrieves wrong tenant's chunks then drops them — leakage risk and wasted work. **Filter in Pinecone query:** candidates are tenant-scoped from the start — VoXgent requirement.

**Follow-up:**

1. **Example VoXgent metadata?**  
   **Say this:** `tenant_id`, `client_id`, `doc_id`, `chunk_index`, `source_uri`, `section_path`, `version`, sometimes `domain: healthcare | sales | support`.

2. **Can filters hurt recall?**  
   **Say this:** Yes — over-filtering excludes the right doc. Test with filter on in eval, not just open search.

---

### Q18. Upsert semantics?

**Say this:**

> **Upsert** = insert or overwrite by **vector ID**. Same ID → new vector and metadata replace the old row. Use **stable IDs** like `docId#chunkIdx` so re-ingest is idempotent — run ingest twice, no duplicates. On VoXgent, document updates bumped version metadata and upserted affected chunks only.

**Compare:**

> **Random UUID per ingest:** duplicates pile up, deletes become guesswork. **Stable deterministic IDs:** safe re-runs and partial updates — production ingest standard.

**Follow-up:**

1. **How do you handle doc deletion?**  
   **Say this:** Delete by metadata filter or list IDs from your chunk registry — source of truth for chunk IDs lives in your DB, not only in Pinecone.

---

### Q19. Cold start empty index?

**Say this:**

> New tenant, empty namespace — query returns **zero vectors**. Handle it in product: polite "I don't have that information yet," **keyword fallback** if configured, and an **operational alert** so CS knows KB ingest failed. Never let the LLM freestyle when retrieval is empty.

**Compare:**

> **Silent empty retrieval + LLM:** hallucination on voice calls — unacceptable for healthcare. **Explicit empty handling + refuse rule:** VoXgent grounding policy.

**Follow-up:**

1. **How do you test this?**  
   **Say this:** Staging tenant with no docs — assert router returns refuse path, not fabricated policy answers.

---

### Q20. Capacity planning basics?

**Say this:**

> Rough storage: **num_chunks × dimensions × 4 bytes** for raw floats, plus **index overhead** — often several× for HNSW graphs. RAM and pod/serverless limits matter at scale. Before a client demo with 100k chunks, estimate vector count and Pinecone cost; don't discover limits live.

**Compare:**

> **Undersized index:** throttling, slow queries, failed upserts. **Right-sized + namespace per tenant:** predictable ops — plan from chunk count after ingestion, not file count alone.

**Follow-up:**

1. **What drives chunk count on VoXgent?**  
   **Say this:** PDF page count, chunk size (512–800 tokens typical), overlap, and whether tables are kept whole — one 200-page policy manual can be thousands of vectors.

---

### Q21. Pinecone serverless vs pod (conceptual)?

**Say this:**

> **Pod-based** Pinecone is **provisioned capacity** — you choose size, predictable performance, more ops thinking. **Serverless** scales with usage — simpler ops, pay for queries and storage, great for variable tenant load. Speak in **trade-offs** — ops simplicity vs cost predictability — not marketing bullets.

**Compare:**

> **Pods:** steady high QPS, you know your load. **Serverless:** multi-tenant SaaS with spiky traffic — fits VoXgent-style many clients, uneven usage.

**Follow-up:**

1. **Which did you use?**  
   **Say this:** Know your project's choice and one reason why — e.g. managed scale without running HNSW ourselves, namespaces per client environment.

---

### Q22. Consistency after upsert?

**Say this:**

> After upsert, vectors are **eventually searchable** — usually within seconds, not necessarily in the same HTTP response. Don't assume read-your-writes in one request unless docs guarantee it. VoXgent ingest returned "accepted" and queried after short delay, or used ingest job status before telling the client "KB is live."

**Compare:**

> **Strong immediate consistency:** rare at ANN scale. **Eventual consistency:** normal — design UX and tests accordingly.

**Follow-up:**

1. **User uploads doc and asks immediately?**  
   **Say this:** Queue ingest async; voice agent says "I'm still learning that document" until job completes — or block QA until index refresh confirms chunk count.

---

### Q23. Backup / rebuild strategy?

**Say this:**

> **Source of truth = original documents** in object storage or DB — not the Pinecone index alone. Vectors are **derived data**. You must be able to **re-embed everything** from source if Pinecone data is lost, model upgrades, or bad ingest corrupts the index. Keep chunk manifests — doc ID, chunk index, text hash — for audit and rebuild.

**Compare:**

> **Vectors only, no pipeline:** one incident = permanent KB loss. **Reproducible ingest pipeline:** rebuild index in hours — VoXgent production hygiene.

**Follow-up:**

1. **Blue/green rebuild steps?**  
   **Say this:** New index/namespace → full re-embed → eval golden questions → flip query routing → delete old index.

---

### Q24. Security?

**Say this:**

> **API keys** in secrets manager, not code. **Private networking** where required. **Per-tenant namespaces or strict metadata filters** — defense in depth. **Encryption** at rest and in transit. **No PII in plaintext metadata** if policy restricts it — put sensitive fields in your DB, not Pinecone filters logs might expose.

**Compare:**

> **Prompt-only isolation:** "only use Client A docs" — model can ignore. **Metadata filter on every query:** enforced by retrieval — VoXgent multi-tenant rule.

**Follow-up:**

1. **Cross-client leakage test?**  
   **Say this:** Query tenant B's agent with tenant A's doc keywords — assert zero results from A's namespace. Automated in CI where possible.

---

## D. Hybrid & Keyword

### Q25. BM25 in one sentence?

**Say this:**

> **BM25** is a keyword ranking function — it scores documents using **term frequency**, **inverse document frequency** (rare words matter more), and **length normalization** so long docs don't win only because they're long. Great for exact tokens like SKUs, error codes, and statute section numbers.

**Compare:**

> **BM25:** lexical, exact, fast, no GPU. **Dense embeddings:** semantic, paraphrase-friendly. **Hybrid:** both lists merged — e.g. RRF — VoXgent pattern for enterprise KBs.

**Follow-up:**

1. **When did BM25 save you?**  
   **Say this:** Queries like "error E-4472" or "Section 12.4.1" — dense alone ranked generic troubleshooting chunks; BM25 hit the exact paragraph.

---

### Q26. When hybrid beats pure vector?

**Say this:**

> Hybrid wins when users search **exact tokens** — part numbers, error codes, person names, legal section IDs, SKU strings — or in **low-resource domains** where the embedding model wasn't trained on your jargon. Voice paraphrases still need dense; exact IDs need sparse.

**Compare:**

> **Pure vector:** natural questions, synonyms, multilingual paraphrase. **Pure BM25:** keyword-heavy search apps. **Hybrid:** real enterprise RAG — VoXgent clients in healthcare and compliance.

**Follow-up:**

1. **Sign hybrid is needed?**  
   **Say this:** Eval shows dense gets semantic questions right but systematically misses ID-style queries — add BM25 + RRF, don't swap embedding model first.

---

### Q27. Implementing hybrid without Elastic?

**Say this:**

> You don't need Elasticsearch. Run **BM25 in Postgres full-text**, a lightweight **rank-bm25** in Python, or a small **OpenSearch** service for sparse. Query **Pinecone for dense** top-k and sparse for top-k **in parallel**, merge with **RRF in the app layer**. LangChain's **EnsembleRetriever** is the same idea — two retrievers, one fused list.

**Compare:**

> **Single Elastic cluster:** dense + sparse in one place — ops heavy. **Pinecone dense + separate BM25 + RRF in FastAPI:** simpler for VoXgent-style stack already on Postgres/GCP.

**Follow-up:**

1. **Latency concern?**  
   **Say this:** Run dense and sparse in parallel with asyncio — total time ≈ max of the two, not sum, if you design for it.

---

## E. Query Understanding

### Q28. Query expansion?

**Say this:**

> **Query expansion** adds synonyms or related terms before search — via LLM, thesaurus, or domain dictionary — to **improve recall** when users use different words than the KB. Risk: **query drift** — expanded terms pull irrelevant chunks. Constrain with **domain dicts** and cap expansions; evaluate on golden questions.

**Compare:**

> **Raw user utterance:** fast, can miss vocabulary mismatch. **LLM expansion:** better recall, can hallucinate off-topic terms — use controlled expansion for regulated domains.

**Follow-up:**

1. **VoXgent voice example?**  
   **Say this:** User says "copay for dentist" — rewrite or expand to include "dental coinsurance" if that's how the policy doc is written — but only after conversational rewrite, not blind LLM fluff.

---

### Q29. Query classification / routing?

**Say this:**

> Before Pinecone, **classify the query**: chitchat → no RAG; KB question → retrieve; account action → **tool** (CRM, schedule); unsafe → block. Saves cost and latency — don't embed and search when the user wants to transfer to a human or check order status via API.

**Compare:**

> **Always retrieve:** wasted Pinecone calls, wrong context confuses LLM. **Router node in LangGraph:** VoXgent pattern — retrieve, tool, or human transfer based on intent.

**Follow-up:**

1. **What if router is wrong?**  
   **Say this:** Low-confidence path → clarify question or human transfer on voice; log for router prompt tuning — separate from retrieval metrics.

---

### Q30. Coreference in conversational query rewrite?

**Say this:**

> In multi-turn voice, users say **"What's the waiting period for that?"** — "that" means nothing to embedding search. **Query rewrite** uses conversation history: → **"What is the waiting period for dental insurance policy X?"** Essential for RAG on VoXgent calls where context carries across turns.

**Compare:**

> **Single-turn retrieval:** embed raw last utterance — fails on pronouns. **Rewrite then embed:** same Pinecone index, much better recall — cheap win before bigger model changes.

**Follow-up:**

1. **Where does rewrite live?**  
   **Say this:** LangGraph node before Pinecone — input: last N turns + current utterance; output: standalone search query; then embed and retrieve.

2. **Rewrite hallucination risk?**  
   **Say this:** Constrain rewrite to compress history, not invent facts — "dental plan we discussed" not "Plan Gold 5000" unless that was said.

---

## F. VoXgent tie-in

### Q31. 45-second embedding/retrieval story?

**Say this:**

> On VoXgent I owned the RAG retrieval layer. We chunked client knowledge — healthcare policies, sales playbooks, support FAQs — embedded each chunk, and upserted to **Pinecone with metadata** for **tenant and domain filtering**. At call time we **rewrote** the user's voice utterance using conversation history, embedded the standalone query, retrieved **top-k** chunks — hybrid when needed for exact IDs — and injected that context into the LLM for grounded answers. Actions like CRM updates or human transfer went through **tools**, not the vector DB. Most quality gains came from **chunking, tenant filters, and retrieval eval** — not prompt tweaks alone.

**Follow-up:**

1. **What would you improve next?**  
   **Say this:** Formal RAGAS-style monitoring in production, optional cross-encoder rerank on top-k, and stronger golden-set regression when clients upload new doc versions.

2. **Biggest mistake you avoided?**  
   **Say this:** Tuning prompts while retrieval was returning wrong chunks — now I always check Recall@k and spot-check citations before touching the system prompt.

---

## Failure diagnosis cheatsheet

| Symptom | Likely cause |
|---------|--------------|
| Always irrelevant chunks | Wrong embed model mix, bad chunking, missing rewrite |
| Good chunks, bad answer | Prompt, temperature, lost-in-middle, no refuse rule |
| Misses exact ID queries | Need hybrid/BM25 |
| Cross-client leakage | Missing tenant filter |
| Sudden quality drop | Model/index version drift, failed ingest |
| High latency | Large k, slow rerank, sync embed calls, no cache |

---

**Related:** `02_RAG_Deep_Dive_QA.md`, `03_Structured_Output_LLM_Integration_Grounding.md`, `04_LangChain_LangGraph_Agents_QA.md`, `06_RAG_Pipeline_Step_by_Step.md`
