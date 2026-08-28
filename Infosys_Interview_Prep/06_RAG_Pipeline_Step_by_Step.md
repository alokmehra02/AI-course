# 06 — RAG Pipeline: Step-by-Step (Ingestion → Answer)

**Purpose:** Deep walkthrough of every RAG stage — ingestion, extraction by file type, chunking, retrieval, generation.  
**Anchor project:** VoXgent.AI (LangChain, LangGraph, Pinecone, voice agents).

---

## How to use this file

| Label | Meaning |
|-------|---------|
| **Say this** | Exact words to speak in the interview |
| **Compare** | Short "X vs Y" — use when they ask *why* |
| **Follow-up** | What they ask next |

Each **STEP** section has technical detail below. **Interview Q&A** blocks give speakable answers — practice those aloud.

---

## Pipeline overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OFFLINE (Ingestion / Indexing)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. Source discovery    → Where docs live (S3, Drive, CRM, DB, uploads)   │
│  2. Ingestion           → Fetch, validate, dedupe, version                  │
│  3. Data extraction     → PDF/DOC/PPT/MD/CSV/images → clean text + metadata │
│  4. Preprocessing       → Normalize, language detect, PII, structure tags   │
│  5. Chunking            → Document-type-aware splits                          │
│  6. Embedding           → Vectors for each chunk                             │
│  7. Indexing            → Upsert to Pinecone with rich metadata              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ONLINE (Query / Answer)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  8. Query preprocessing → Rewrite, classify, tenant filter                  │
│  9. Retrieval           → Vector (+ optional hybrid) search                  │
│ 10. Reranking           → Cross-encoder / score filter                       │
│ 11. Context assembly    → Pack chunks, citations, token budget             │
│ 12. Generation          → LLM with grounded prompt                           │
│ 13. Post-processing     → Validate citations, structured output, handoff   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Interview one-liner:** Ingestion quality and chunking decide 70% of RAG success; the LLM only fixes what retrieval already made possible.

---

# STEP 1 — Source Discovery & Ingestion

## What happens

Before parsing anything, you define **where knowledge comes from** and **how it enters the pipeline**.

## Typical sources (enterprise / VoXgent-style)

| Source | Examples | Notes |
|--------|----------|-------|
| File uploads | PDF, DOCX, PPT, CSV | Admin portal, client onboarding |
| Cloud storage | S3, GCS, Azure Blob | Batch sync jobs |
| Wikis / CMS | Confluence, SharePoint | API crawl + webhooks on update |
| CRM / EMR | Salesforce, Canvas EMR | Export or API pull |
| Databases | PostgreSQL, MongoDB | Structured rows → text records |
| Google Sheets | FAQs, product lists | Sheets API → row objects |
| Web pages | Help center URLs | Crawler with allowlist |

## Ingestion workflow

```
1. List / watch source (cron, webhook, Pub/Sub event)
2. Download raw file → store in object storage (immutable copy)
3. Compute hash (SHA-256) → skip if unchanged
4. Assign doc_id, tenant_id, version, source_uri
5. Enqueue parse job (Cloud Tasks / Celery / worker queue)
6. On success → mark indexed; on failure → retry + dead-letter + alert
```

## What you validate at ingestion

- **File type** (magic bytes, not just extension — `.pdf` that is actually `.docx`)
- **Size limits** (reject 500MB PDFs or split processing)
- **Tenant ownership** (client A docs never tagged as client B)
- **ACL / sensitivity** (PII, HIPAA, internal-only flags in metadata)
- **Language** (route to correct embedding / translation if needed)
- **Duplicate detection** (same content, different filename)

## Interview answer

> "Ingestion is not just upload. We store an immutable raw copy, assign stable `doc_id` and `tenant_id`, dedupe by content hash, and enqueue async workers so parsing never blocks the API. Every document gets version metadata so updates trigger re-index, not silent stale answers."

---

## Interview Q&A — Step 1 (Ingestion)

### Q. What happens in the ingestion step?

**Say this:**

> Ingestion is where files enter the system. We download from upload, S3, or an API, save a raw copy, assign `doc_id` and `tenant_id`, check file type and size, skip duplicates using a hash, and push a job to a queue. Parsing runs in the background so the API stays fast. On VoXgent, client healthcare and sales docs went through this before they ever hit Pinecone.

**Compare:**

> **Sync upload + parse in API** = slow, timeouts. **Queue-based ingestion** = same pattern as our GCP Pub/Sub workers — reliable at scale.

**Follow-up:**

1. **How do you handle document updates?**  
   **Say this:** > Bump `doc_version`, delete old vectors for that `doc_id`, re-parse, re-embed, upsert. Never leave old chunks sitting in Pinecone.

2. **What if the same file uploads twice?**  
   **Say this:** > Hash match — skip re-processing unless the client forces a refresh.

---

# STEP 2 — Data Extraction (Parsing) by File Type

**Goal:** Turn every format into **structured text + metadata** that chunking can use. One parser does not fit all.

---

## 2A. PDF (most common in enterprise RAG)

### Subtypes you must handle

| PDF type | Problem | Approach |
|----------|---------|----------|
| **Digital / text PDF** | Selectable text | Direct text extraction |
| **Scanned PDF** | Image pages, no text layer | OCR |
| **Mixed PDF** | Some pages text, some scan | Page-level detection |
| **PDF with tables** | Rows/columns break when flattened | Table extraction |
| **PDF with images/diagrams** | Facts live in figures | OCR + vision caption |
| **Multi-column layouts** | Reading order wrong | Layout-aware parser |

### Tools / libraries (Python ecosystem)

- **PyMuPDF (fitz)** — fast text + layout, page boundaries
- **pdfplumber** — good for tables
- **Unstructured.io** — unified pipeline, layout elements
- **LlamaParse / Azure Document Intelligence** — production OCR + layout
- **Tesseract OCR** — fallback for scans (lower quality on handwriting)

### Extraction pipeline for PDF

```
PDF file
  → For each page:
      1. Detect if text layer exists (char count threshold)
      2. If text layer → extract with layout (blocks, headings)
      3. If scan → OCR page image (300 DPI typical)
      4. Detect tables → extract as Markdown tables or row JSON
      5. Detect figures → save image ref + run vision model caption
      6. Attach metadata: page_number, section_title, bbox if available
  → Merge into ordered document elements (title, heading, paragraph, table, figure)
```

### Metadata to preserve

```json
{
  "doc_id": "policy_2024_v3",
  "page": 12,
  "section": "Coverage Limits",
  "element_type": "table",
  "source_uri": "s3://bucket/policy.pdf"
}
```

### Common PDF failures

- Headers/footers repeated on every page → strip before chunking
- Broken reading order in multi-column docs
- Tables become gibberish single lines
- Scanned handwriting → low OCR accuracy → flag for human review or exclude

---

## 2B. DOC / DOCX (Microsoft Word)

### Characteristics

- Rich structure: headings (H1–H6), lists, tables, footnotes
- Often the **source of truth** for policies and SOPs
- Easier than PDF when you get native `.docx` (XML inside)

### Extraction approach

```
DOCX
  → python-docx / Unstructured / mammoth
  → Walk document tree:
      - Heading styles → section boundaries
      - Paragraphs → body text
      - Tables → Markdown or row-wise text with headers
      - Images → extract binary + optional caption/OCR
  → Output: ordered list of {type, text, heading_path, style_level}
```

### Why DOCX is better for chunking than PDF

> Heading styles give you **natural section boundaries** without guessing layout. Chunk by `Heading 2` sections instead of arbitrary 512-token windows.

### Interview line

> "When clients give us DOCX policy docs, we parse by heading hierarchy so a chunk never splits mid-clause — critical for healthcare and compliance answers."

---

## 2C. PPT / PPTX (PowerPoint)

### Characteristics

- Knowledge is **sparse per slide** (bullets, speaker notes, diagrams)
- One slide ≠ one chunk always (title slides vs dense content slides)
- Diagrams and charts carry meaning not in bullet text

### Extraction approach

```
PPTX
  → python-pptx / Unstructured
  → For each slide:
      1. Slide number + title
      2. All text shapes (title, body, text boxes)
      3. Speaker notes (often richer than on-slide text)
      4. Tables on slide
      5. Images/charts → extract + vision caption ("Bar chart: Q3 revenue up 12%")
  → Output element per slide or per slide-section
```

### Chunking implication

| Slide type | Chunk strategy |
|------------|----------------|
| Title-only | Merge with next slide or skip |
| Bullet slide | One chunk = slide title + bullets + notes |
| Diagram-heavy | Chunk = caption + OCR text + slide title |
| Appendix deck | Tag `domain=appendix`, lower retrieval priority |

### Example extracted unit

```text
[Slide 7 — Product Pricing]
Title: Enterprise Tier Features
Bullets: Unlimited agents; SSO; SLA 99.9%
Speaker notes: Enterprise tier starts at $X/month, minimum 50 seats...
[Figure caption]: Pricing comparison table — Basic vs Pro vs Enterprise
```

---

## 2D. Markdown (.md)

### Characteristics

- Already structured (`#`, `##`, code blocks, tables)
- Common in internal docs, Git repos, technical KB

### Extraction approach

```
MD file
  → Parse AST (markdown-it, mistune, or LangChain MarkdownHeaderTextSplitter)
  → Preserve:
      - Header hierarchy (# → ######)
      - Code blocks as separate elements (don't split mid-code)
      - Tables as Markdown blocks
      - Links (store URL in metadata)
  → Minimal cleaning needed — structure is explicit
```

### Chunking

> **Best case:** split on `##` or `###` headers. Keep code blocks intact in one chunk. Never split a fenced code block across chunks.

---

## 2E. CSV / Excel (structured data)

### Characteristics

- Not prose — rows and columns
- RAG needs **row-level or record-level** text, not raw CSV lines
- Great for product catalogs, FAQs, price lists, EMR exports

### Extraction approach

```
CSV / XLSX
  → pandas / openpyxl
  → For each row (or logical record):
      Convert to natural language or key-value text:

      Row: id=101, product=Widget A, price=49.99, category=Hardware
      → Text: "Product Widget A (ID 101) is in category Hardware, priced at $49.99."

  → Or template: "{column}: {value}" joined per row
  → Metadata: row_id, sheet_name, source_table
```

### When NOT to chunk CSV like prose

> Don't run recursive character splitter on CSV — you'll cut mid-row. **One row (or grouped related rows) = one chunk** with column headers repeated in text for context.

### Multi-sheet Excel

```
Workbook
  → Each sheet = different entity type (Products, FAQs, Contacts)
  → Tag metadata sheet_name + entity_type
  → Index separately or filter at query time
```

---

## 2F. HTML / Web pages

```
HTML
  → BeautifulSoup / trafilatura / Readability
  → Remove nav, footer, ads, scripts
  → Keep: title, h1-h6, main content, tables
  → Store canonical URL + last_crawled timestamp
```

---

## 2G. Plain text (.txt)

```
TXT
  → Encoding detection (UTF-8, Latin-1)
  → Split on blank lines or fixed sections if markers exist
  → Minimal parsing — often logs or exports
```

---

## 2H. Images (PNG, JPG, TIFF, diagrams in PDF/PPT)

### When images matter in RAG

- Scanned pages (PDF as image)
- Architecture diagrams, flowcharts
- Charts with data not duplicated in text
- Handwritten notes (medical forms, field notes)

### Extraction pipeline

```
Image
  → Optional: classify (photo vs diagram vs table vs handwriting)
  → Branch:
      - Printed text → OCR (Tesseract, Azure DI, Google Vision)
      - Handwriting → specialized HWR model
      - Diagram/chart → Vision LLM caption:
          "Flowchart showing: User calls → IVR → RAG agent → Human transfer"
      - Table in image → table OCR or vision extraction to Markdown
  → Store:
      - extracted_text
      - caption (searchable)
      - image_ref (for UI display at answer time)
      - modality: "image"
```

### Indexing images in vector DB

Two common patterns:

1. **Caption + OCR text embedded** (simplest) — query hits text description
2. **Multimodal embeddings** (CLIP-style) — image and text in same space

For VoXgent-style voice agents, **caption + OCR as text chunks** is the practical default.

### Interview answer (Infosys-style messy docs)

> "Images aren't a separate problem from RAG — they're a modality problem. We OCR printed text, use vision models to describe diagrams, and index the description as searchable text while keeping the image reference for the UI. Plain chunking on PDF text alone would miss answers that live only in a chart."

---

## 2I. JSON / API responses (CRM, EMR, Sheets)

```
JSON record
  → Flatten nested fields to readable text
  → Example Salesforce Lead:
      "Lead John Doe, company Acme, status Qualified, owner Jane Smith"
  → Metadata: object_type, record_id, last_modified
  → Short TTL re-sync for live data; RAG for static KB, tools for live CRM
```

**Rule:** Frequently changing live records → **tool/API at query time**. Static exports → **RAG index**.

---

## 2J. Unified extraction architecture (production)

```
                    ┌─────────────────┐
                    │  Raw file/API   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Type router    │
                    │  (by MIME/ext)  │
                    └────────┬────────┘
         ┌──────────┼──────────┼──────────┐
         ▼          ▼          ▼          ▼
     PDF parser  DOCX parser PPT parser CSV parser
         │          │          │          │
         └──────────┴──────────┴──────────┘
                             │
                    ┌────────▼────────┐
                    │ DocumentElement │
                    │ list (typed)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Preprocessor    │
                    └─────────────────┘
```

Each parser outputs the **same internal schema**:

```python
DocumentElement = {
    "text": str,
    "type": "paragraph | heading | table | figure | list | row",
    "metadata": {
        "doc_id", "tenant_id", "page", "slide", "section_path",
        "element_index", "source_uri", "created_at", "doc_version"
    }
}
```

---

## Interview Q&A — Step 2 (Extraction by file type)

### Q. How do you extract text from PDF, DOC, PPT, CSV, and images?

**Say this:**

> I route by file type. PDF — layout parser for digital text, OCR for scans, separate handling for tables and figures. DOCX — parse by heading styles so sections stay intact. PPT — each slide plus speaker notes and chart captions. CSV — each row becomes a text record with column names, not raw comma lines. Images — OCR for text plus a vision model caption for diagrams. Everything lands in the same internal format before chunking.

**Compare:**

> **One generic text splitter on all files** = tables and slides break. **Type-specific parsers** = answers come from the right part of the doc — Infosys clients often ask about messy PDFs for this reason.

**Follow-up:**

1. **Scanned PDF with handwriting?**  
   **Say this:** > OCR for print, handwriting model for notes, vision caption for diagrams. Index the caption as searchable text. Test on messy samples — clean PDFs hide real failures.

2. **Why not only PyMuPDF for everything?**  
   **Say this:** > PyMuPDF is great for text PDFs. Scans need OCR, tables need pdfplumber or similar, PPT needs python-pptx. One tool rarely covers all enterprise formats.

3. **PPT vs PDF for training decks?**  
   **Say this:** > PPT gives slide boundaries and speaker notes — chunk per slide. PDF export of slides loses notes unless you parse both layers.

---

# STEP 3 — Preprocessing (after extraction, before chunking)

## What you do

| Task | Why |
|------|-----|
| **Unicode normalize** | Fix smart quotes, broken chars |
| **Whitespace cleanup** | Collapse excessive newlines |
| **Header/footer removal** | PDF page noise |
| **Language detection** | Route embedding model / translation |
| **PII redaction** | Mask SSN, phone if policy requires |
| **Boilerplate removal** | "Confidential", page numbers |
| **Structure tagging** | Mark tables, lists, code |
| **Token count estimate** | Plan chunk sizes |

## Section path (critical for chunking)

Build a breadcrumb from headings:

```
section_path: ["Employee Handbook", "Benefits", "Dental Coverage"]
```

Stored in metadata → better citations: *"Employee Handbook > Benefits > Dental Coverage, page 12"*

---

## Interview Q&A — Step 3 (Preprocessing)

### Q. What do you do after extraction and before chunking?

**Say this:**

> Clean the text — fix encoding, remove repeated PDF headers and footers, detect language, tag sections with a path like Handbook > Benefits > Dental, and redact PII if the client requires it. This step is boring but it stops garbage from entering Pinecone. Bad preprocessing means good chunking still retrieves junk.

**Follow-up:**

1. **What is section_path?**  
   **Say this:** > Breadcrumb from headings — helps citations and section-based chunking on DOCX and Markdown.

2. **PII in healthcare docs?**  
   **Say this:** > Mask at ingest when possible, strict ACL in metadata, minimal logging. Follow client rules before sending text to external LLMs.

---

# STEP 4 — Chunking (document-type-aware)

**Chunk = smallest retrievable unit of meaning.** Wrong chunking = right embedding model still fails.

---

## 4A. Core chunking parameters

| Parameter | Typical range | Notes |
|-----------|---------------|-------|
| **Chunk size** | 256–1024 tokens | Smaller for FAQ; larger for narrative |
| **Overlap** | 10–20% of chunk size | Preserves boundary facts |
| **Separator priority** | `\n\n` → `\n` → `.` → ` ` | Recursive splitting |
| **Min chunk size** | ~50 tokens | Drop or merge tiny fragments |

---

## 4B. Chunking strategy by document type

### PDF — Policy / legal / healthcare

```
Strategy: Layout-aware + section-based
1. Prefer heading/section boundaries from parser
2. If no headings: recursive split with overlap
3. Tables: keep entire table in ONE chunk (or header + row groups)
4. Figures: caption + OCR as standalone chunk linked to section_path
5. Parent-child: small child chunks for retrieval, parent section for generation
```

**Why:** Legal/policy answers need full clauses — never split *"Coverage excludes X unless Y"* across two chunks.

---

### DOCX — SOPs, manuals

```
Strategy: MarkdownHeaderTextSplitter equivalent
- Split on Heading 1 / 2 / 3
- Max chunk size cap (e.g. 800 tokens) — sub-split large sections
- Overlap only within same section, not across sections
- Lists: keep full list in one chunk if under size cap
```

---

### PPT — Sales decks, training

```
Strategy: Slide-centric
- Default: 1 slide = 1 chunk (title + body + notes + figure caption)
- Dense slides: split bullets into 2 chunks sharing same slide metadata
- Skip empty title slides
- Metadata: slide_number, deck_name
```

---

### Markdown — Technical docs

```
Strategy: Header hierarchy
- Split on ## or ### depending on doc depth
- Code blocks: never split; one block = part of one chunk
- API docs: split per endpoint section
```

---

### CSV / Excel — Catalogs, FAQs

```
Strategy: Row / record chunking
- 1 row → 1 chunk (with headers inlined in text)
- Wide rows: group related columns
- FAQ sheet: Question + Answer in same chunk always
- No character-based recursive split
```

Example FAQ chunk:

```text
Q: What is the waiting period for dental coverage?
A: Dental coverage has a 90-day waiting period for new enrollments.
Metadata: row_id=42, sheet=FAQ, category=benefits
```

---

### HTML — Help center

```
Strategy: Article / section based
- One help article = 1–N chunks by H2 sections
- Strip nav; chunk only `<main>` content
```

---

### Images (standalone or embedded)

```
Strategy: One visual unit = one chunk
- chunk_text = OCR_text + "\n" + vision_caption
- metadata.modality = "image"
- Optional: link parent doc_id + page
```

---

### JSON / CRM exports

```
Strategy: Record chunking
- 1 business record = 1 chunk
- Include type label: "Salesforce Account record: ..."
```

---

## 4C. Advanced chunking patterns

### Parent–child (small-to-big)

```
Parent: entire "Dental Benefits" section (2000 tokens) — stored, not always retrieved
Child: 400-token sub-chunks — retrieved by similarity
On hit: expand to parent for LLM context
```

**Use when:** Sections are long but answers need local precision + broader context.

### Semantic chunking

```
Embed sentences → split when cosine similarity between adjacent sentences drops
```

**Use when:** No headings, narrative text. **Cost:** more embedding calls at ingest.

### Agentic chunking (experimental)

```
LLM proposes split points given document structure
```

**Use sparingly** — cost/latency at ingest; good for high-value docs only.

---

## 4D. What every chunk record looks like (before embedding)

```json
{
  "chunk_id": "policy_v3_p12_c004",
  "doc_id": "policy_v3",
  "tenant_id": "client_healthcare_01",
  "text": "Dental coverage includes preventive care. Waiting period is 90 days...",
  "token_count": 412,
  "metadata": {
    "source_uri": "s3://kb/policy_v3.pdf",
    "doc_type": "pdf",
    "page": 12,
    "section_path": ["Benefits", "Dental"],
    "element_type": "paragraph",
    "doc_version": 3,
    "language": "en",
    "indexed_at": "2026-08-28T10:00:00Z"
  }
}
```

---

## Interview Q&A — Step 4 (Chunking)

### Q. How do you chunk different document types?

**Say this:**

> Chunking depends on the doc. PDF policies — by section or heading, not blind 500-token cuts. DOCX — split on Heading 2 or 3. PPT — usually one slide per chunk including notes. CSV — one row or one FAQ pair per chunk with headers in the text. Markdown — split on headers, never break a code block. Tables stay whole in one chunk. For long sections we used parent-child — small chunk for search, big parent for context.

**Compare:**

> **Fixed 512 tokens for everything** = splits mid-sentence in policies. **Document-aware chunking** = retrieval finds the right clause — on VoXgent that mattered more than changing the LLM model.

**Follow-up:**

1. **Chunk size for voice agents?**  
   **Say this:** > Smaller than chat — around 300–600 tokens, 10–20% overlap. Voice needs tight context and low latency.

2. **Parent-child chunking in one line?**  
   **Say this:** > Search hits a small chunk; we expand to the parent section when building the prompt so the model sees full context.

3. **CSV chunking mistake to avoid?**  
   **Say this:** > Never run recursive character split on CSV — you cut rows in half. One row = one chunk with column names written out.

---

# STEP 5 — Embedding

## What happens

Each chunk's `text` → embedding model → float vector (e.g. 1536 dims).

## Rules

1. **Same model** for all chunks and all queries (same version)
2. **Batch** chunks (50–200 per API call) for ingest speed
3. **Normalize** — use metric Pinecone expects (cosine/dot)
4. **Instruction prefixes** if model requires (`passage:`, `query:`)
5. **Retry** on 429 with exponential backoff

## Optional: embed multiple fields

Some teams embed `title + section_path + text` concatenated for better retrieval:

```text
"Benefits > Dental | Dental coverage includes preventive care..."
```

---

## Interview Q&A — Step 5 (Embedding)

### Q. How do you generate and store embeddings?

**Say this:**

> Each chunk text goes through an embedding model — same model and version for all chunks and for queries at search time. We batch 50–200 chunks per API call to speed up ingest, retry on rate limits, and store the vector with chunk metadata. Never mix two embedding models in one index.

**Compare:**

> **One HTTP call per chunk** = slow ingest. **Batch embedding** = what we did on VoXgent onboarding — cuts hours to minutes.

**Follow-up:**

1. **Can you use different models for query and document?**  
   **Say this:** > No — unless they are a matched pair trained for that. Usually same model both sides.

2. **What if you upgrade the embedding model?**  
   **Say this:** > Full re-embed all chunks and rebuild the index — blue/green cutover. No shortcut.

---

# STEP 6 — Indexing (Vector DB — Pinecone)

## Upsert flow

```
For each chunk:
  id = chunk_id (stable)
  values = embedding vector
  metadata = { tenant_id, doc_id, page, section_path, doc_type, ... }
  → pinecone.upsert(vectors=[...], namespace=tenant_or_env)
```

## Index design

| Decision | Recommendation |
|----------|----------------|
| **Namespace** | Per tenant or per environment (dev/prod) |
| **Metadata filters** | Always filter `tenant_id` + optional `domain`, `doc_type` |
| **ID scheme** | `{doc_id}#{chunk_index}` for idempotent updates |
| **Delete on update** | Delete all vectors where `doc_id=X` then re-upsert |

## Post-index checks

- Chunk count matches expectation
- Sample query returns relevant chunks
- No cross-tenant leakage in test queries

---

## Interview Q&A — Step 6 (Indexing)

### Q. How do you index chunks in Pinecone?

**Say this:**

> Upsert each chunk with a stable `chunk_id`, the embedding vector, and metadata — `tenant_id`, `doc_id`, page, section, doc version. We used namespaces or filters per client so search always scopes to the right tenant. On update, delete all vectors for that `doc_id` first, then upsert fresh chunks.

**Compare:**

> **FAISS on disk** = fine for a laptop demo. **Pinecone** = managed filters and scale — why we picked it on VoXgent to ship faster without running vector DB ops ourselves.

**Follow-up:**

1. **Namespace vs metadata filter?**  
   **Say this:** > Namespace is a hard partition — often per tenant. Filter is query-time — domain, doc type. We used both.

2. **How prevent client A seeing client B data?**  
   **Say this:** > Mandatory `tenant_id` filter on every query from auth token — never trust the prompt alone.

---

# STEP 7 — Query preprocessing (online pipeline starts)

## Steps

```
User utterance (+ conversation history)
  → 1. Auth → resolve tenant_id
  → 2. Safety filter (block harmful requests)
  → 3. Intent classify: chitchat | KB_question | tool_action | human_transfer
  → 4. If KB_question:
         Query rewrite (resolve "that policy", "it" from history)
         Optional: multi-query generation
  → 5. Embed query (same model as index)
```

## Voice-specific (VoXgent)

> STT output is noisy — rewrite step fixes "dental waiting period" from "dental waiting priod". Short utterances benefit from HyDE or multi-query more than long chat messages.

---

## Interview Q&A — Step 7 (Query preprocessing)

### Q. What happens to the user query before retrieval?

**Say this:**

> After auth we know `tenant_id`. We classify intent — chitchat, knowledge question, tool action, or human transfer. For KB questions we rewrite the query using recent chat history so "what about the waiting period for that" becomes a full search query. Then we embed the rewritten query with the same model as the index.

**Compare:**

> **Embed raw user text only** = fails on follow-up questions in voice. **Rewrite then embed** = much better recall — LangGraph had a dedicated rewrite node before Pinecone on VoXgent.

**Follow-up:**

1. **When skip RAG entirely?**  
   **Say this:** > Greetings, or when user wants an action like "book appointment" — route to tools not vector search.

2. **Voice vs chat preprocessing?**  
   **Say this:** > Voice has STT errors — rewrite and normalize matter more. Keep history short for latency.

---

# STEP 8 — Retrieval

```
Embedded query
  → Vector search top_k=20 (with metadata filters)
  → Optional: BM25 parallel search → RRF merge (hybrid)
  → Optional: MMR for diversity
  → Score threshold: drop chunks below 0.72 (calibrate on eval set)
```

## Filter examples

```python
filter = {
    "tenant_id": "client_01",
    "domain": {"$in": ["healthcare", "general"]},
    "doc_version": {"$gte": 2}
}
```

---

## Interview Q&A — Step 8 (Retrieval)

### Q. How does retrieval work at query time?

**Say this:**

> Embed the query, search Pinecone for top-k similar chunks with tenant and domain filters, optionally merge with keyword search for product codes, drop chunks below a score threshold, and pass candidates to reranking or straight to context assembly. On VoXgent, k was kept small for voice — often 5 to 8 before cutting down to 3 for the prompt.

**Compare:**

> **Dense vector only** = misses exact codes like "Policy 12.3". **Hybrid dense + BM25** = better for enterprise docs — we used hybrid on some clients.

**Follow-up:**

1. **How pick top-k?**  
   **Say this:** > Start with eval data — too low misses facts, too high adds noise and latency. Voice stays on the lower end.

2. **What if retrieval returns nothing?**  
   **Say this:** > Say I don't know, try rewrite once in LangGraph, then human transfer — don't let the model guess.

---

# STEP 9 — Reranking

```
20 candidates → cross-encoder rerank → top 3–5 for prompt
```

**Skip rerank** if latency budget tight (voice) — tune k and chunk quality instead.

---

## Interview Q&A — Step 9 (Reranking)

### Q. What is reranking and when do you use it?

**Say this:**

> First retrieval uses embeddings — fast but rough. Reranking scores each query-chunk pair with a cross-encoder — slower but more accurate. Typical pattern: retrieve 20, rerank to top 3 for the prompt. On voice we sometimes skipped rerank to save latency and relied on better chunking and filters instead.

**Compare:**

> **Bi-encoder (embedding)** = fast, used on millions of chunks. **Cross-encoder rerank** = accurate, used on 20 candidates only — you can't rerank the whole index.

**Follow-up:**

1. **Voice agent skip rerank?**  
   **Say this:** > Yes when p95 latency is tight — improve chunking and k first, add rerank only if quality still suffers.

---

# STEP 10 — Context assembly

```
1. Sort final chunks by relevance (or section order for narrative)
2. Deduplicate near-identical chunks
3. Build context block:

   ### Source 1 (policy_v3, p12, Benefits > Dental)
   {chunk text}

   ### Source 2 (...)

4. Track allowed citation IDs = only these chunk_ids
5. Trim to token budget (drop lowest scores first)
```

## Lost-in-the-middle mitigation

> Put **highest-scoring chunk first** and second-best last; or keep only 3–5 chunks for voice.

---

## Interview Q&A — Step 10 (Context assembly)

### Q. How do you build the context block for the LLM?

**Say this:**

> Take the final 3 to 5 chunks, dedupe similar ones, label each with source id and page, build a CONTEXT section in the prompt, and track allowed citation ids — only those chunk ids can appear in the answer. Trim to token budget by dropping lowest scores first. Put the best chunk at the start because models sometimes ignore the middle of long context.

**Follow-up:**

1. **Lost in the middle?**  
   **Say this:** > Models miss facts buried in the center of a long prompt — keep context short, best chunks first.

2. **Citation allowlist?**  
   **Say this:** > Pass retrieved chunk ids to validation — model cannot cite a doc that was not in context.

---

# STEP 11 — Generation (LLM)

## Prompt structure

```
SYSTEM:
You are a support agent for {client}. Answer ONLY using Context below.
If Context does not contain the answer, say you don't know and offer human transfer.
Cite sources using [Source N]. Do not invent policies.

CONTEXT:
{assembled chunks}

HISTORY:
{last 2-4 turns}

USER:
{question}
```

## Parameters

- `temperature`: 0–0.3 for factual
- Structured output optional: `{ answer, citations[], grounded, needs_human }`

---

## Interview Q&A — Step 11 (Generation)

### Q. How do you prompt the LLM for grounded answers?

**Say this:**

> System message sets the role and rules — answer only from CONTEXT, say I don't know if missing, cite sources. CONTEXT holds retrieved chunks. User message holds the question. Temperature low — 0 to 0.3 for facts. On VoXgent we also returned structured fields like `needs_human` for routing in LangGraph.

**Compare:**

> **Prompt only, no RAG** = model guesses from training. **RAG + strict prompt** = answer tied to client docs — but only if retrieval brought the right chunks.

**Follow-up:**

1. **What if context contradicts itself?**  
   **Say this:** > Prefer newest doc_version in metadata, flag conflict, escalate to human in healthcare.

2. **LangChain vs LangGraph here?**  
   **Say this:** > LangChain prompt template inside the generate node — LangGraph decides whether to generate, call tool, or transfer after this step.

---

# STEP 12 — Post-processing & guardrails

```
LLM output
  → Validate citations ⊆ retrieved chunk_ids
  → Faithfulness check (optional NLI / LLM judge)
  → If low confidence → needs_human = true → Twilio transfer
  → Log: query, chunk_ids, scores, latency, model
  → Return answer + citations to client / voice layer
```

---

## Interview Q&A — Step 12 (Post-processing)

### Q. What happens after the LLM generates an answer?

**Say this:**

> Validate citations against retrieved chunk ids, optional faithfulness check, if confidence is low set needs_human and trigger Twilio transfer, log query chunk ids scores and latency, return answer to voice or API. Never write to CRM without validating structured output — we learned that on Salesforce integrations.

**Compare:**

> **Demo chatbot** = show text and done. **Production VoXgent** = validate, log, escalate — Infosys JD asks about production issues; this step is where you catch bad answers before the client does.

**Follow-up:**

1. **Hallucinated citation?**  
   **Say this:** > Reject output if cited id was not in retrieved set — retry once or transfer to human.

2. **Prompt injection in retrieved doc?**  
   **Say this:** > Treat context as untrusted data — system rules override text that says ignore previous instructions.

---

# End-to-end example (healthcare FAQ PDF)

```
1. Client uploads policy.pdf (scanned + digital mix)
2. Ingestion: store S3, doc_id=hc_policy_v1, tenant=clinic_a
3. Extraction:
   - Pages 1-5: digital text via PyMuPDF
   - Pages 6-10: OCR
   - Page 8: table → Markdown table element
   - Page 9: diagram → vision caption
4. Preprocess: strip footers, section_path from headings
5. Chunk:
   - Section "Dental" → 3 child chunks (400 tokens, 50 overlap)
   - Table on p8 → 1 chunk (whole table)
   - Figure on p9 → 1 chunk (caption + OCR)
6. Embed: text-embedding-3-small, batches of 100
7. Index: Pinecone namespace clinic_a, metadata filters
--- user call ---
8. Query: "What's the dental waiting period?"
9. Rewrite: same (clear question)
10. Retrieve: top 5, filter tenant=clinic_a
11. Rerank: top 3
12. Context: 2 chunks include "90-day waiting period"
13. Generate: "Dental coverage has a 90-day waiting period [Source 1]."
14. Post: citations valid, grounded=true, log metrics
```

---

# Master interview question: "Walk me through your RAG pipeline"

### Q. Explain your full RAG pipeline end to end.

**Say this:**

> We split offline and online. Offline: client uploads or integrations bring in PDF, DOCX, PPT, CSV, images — we store raw files with doc_id and tenant_id, route each type to its parser, OCR scans, caption diagrams, preprocess, chunk by document type, batch embed, upsert to Pinecone with metadata filters. Online: auth, rewrite query from voice or chat history, embed, retrieve with tenant filter, optional rerank, pack context with citation ids, generate with strict grounded prompt, validate output, human transfer if low confidence. On VoXgent, LangGraph wired the online steps — retry retrieval, tools, Twilio transfer. Most wins were ingestion and chunking, not swapping the LLM.

**Compare:**

> **LangChain-only linear chain** = retrieve then answer once. **LangGraph on top** = same RAG index, but loops and branches for production voice — that is why we used both on VoXgent.

**Follow-up:**

1. **Which step breaks most often?**  
   **Say this:** > Retrieval and chunking — wrong chunk in the prompt means a smart model still gives wrong answers.

2. **Biggest lesson from production?**  
   **Say this:** > Measure retrieval before tuning prompts. Fix tenant filters and chunk boundaries first.

3. **How long from upload to searchable?**  
   **Say this:** > Async workers — target minutes not hours, depends on doc size; critical updates can get priority queue.

---

# Checklist before saying "RAG is done"

- [ ] Every file type has a dedicated parser route
- [ ] Scanned PDFs and images handled (OCR + caption)
- [ ] Tables not flattened to garbage
- [ ] Chunking rules per doc type documented
- [ ] tenant_id on every vector + query filter tested
- [ ] doc_version + re-index on update
- [ ] Golden eval set with table/image/handwriting cases
- [ ] Latency budget met for voice/chat
- [ ] Citation allowlist enforced
- [ ] Human fallback path tested

---

**Related docs:** `02_RAG_Deep_Dive_QA.md` · `03_Structured_Output_LLM_Integration_Grounding.md` · `05_Embeddings_VectorDB_Retrieval_QA.md`
