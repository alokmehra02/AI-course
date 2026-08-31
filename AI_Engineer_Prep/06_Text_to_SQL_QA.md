# 06 — Text-to-SQL Q&A

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask  
**Focus:** Schema injection, pruning, guardrails, self-correction, production safety.  
**Anchor project:** Europa / enterprise analytics style — read-only replica, sqlglot AST, LangGraph loop; VoXgent analog for operational reporting.

---

## A. Architecture fundamentals

### Q1. What is text-to-SQL and when use it?

**Say this:**

> Text-to-SQL converts natural language to SQL so non-analysts get ad-hoc answers from relational data. Architecture: user question → schema context + LLM → SQL → validate → execute on read-only DB → return table or summary. Good for **exploratory analytics** on structured data — "top 10 customers by revenue last quarter."

**Compare:**

> RAG on PDFs = unstructured docs. Text-to-SQL = **live structured data** with joins and aggregates. Different pipeline; often complementary in one product.

**Follow-up:**

1. **VoXgent / Europa style?**  
   **Say this:** Voice agent might answer from RAG policies; back-office Europa-style dashboard lets ops ask SQL over call metrics and campaign tables — same guardrail mindset, different UX.

---

### Q2. Schema injection — what do you put in the prompt?

**Say this:**

> Inject **DDL** — CREATE TABLE with columns, types, keys — plus **column comments**, **foreign keys**, and **2–3 sample rows** per table so the model sees real formats. Generated via SQLAlchemy inspector or information_schema. Without schema, the model hallucinates table names.

**Compare:**

> Full schema vs pruned schema — full works for 10 tables; 200 tables need dynamic pruning or you hit context limits and "lost in the middle."

**Follow-up:**

1. **Token cost?**  
   **Say this:** Schema is static per query batch — cache pruned schema in Redis keyed by retrieved table set.

---

### Q3. Dynamic schema pruning — how?

**Say this:**

> Embed table metadata (name, description, columns) in a vector index. Embed user question, retrieve top K tables (5–10), inject only those DDLs. **Dependency expansion:** if `orders` retrieved, pull `customers` via FK graph even if lower similarity. Prevents join failures from missing parent table.

**Compare:**

> Keyword match on table names = fast but misses synonyms. Vector search = semantic "revenue" → `sales_fact`. Always merge FK neighbors.

**Follow-up:**

1. **Common mistake?**  
   **Say this:** Top-K only without FK closure — model writes join to missing table.

---

### Q4. Dialect-specific prompting — why?

**Say this:**

> PostgreSQL ≠ MySQL ≠ BigQuery. `LIMIT` vs `TOP`, `DATE_TRUNC` vs `STR_TO_DATE`, identifier quotes differ. System prompt states dialect explicitly; add **few-shot** pairs of question → SQL for your domain. Dynamically retrieve similar past queries from a vector store for better few-shots.

**Follow-up:**

1. **Wrong dialect symptom?**  
   **Say this:** Query parses in validator but fails at execution — `DATE_TRUNC` on MySQL. Catch in self-correction loop with DB error feedback.

---

### Q5. Read-only replica — non-negotiable?

**Say this:**

> Yes for production. LLM connects to **read replica** with DB user that has **SELECT only**. Even with AST checks, defense in depth — replica lag acceptable for analytics; primary never touched. Separate credentials from app write pool.

**Compare:**

> Prompt "only SELECT" is not security. Replica + AST + timeout is.

**Follow-up:**

1. **Staging vs prod?**  
   **Say this:** Same pattern in staging with masked data — never point text-to-SQL at prod primary "just for demo."

---

## B. Guardrails & execution

### Q6. AST validation with sqlglot — how?

**Say this:**

> Parse generated SQL with **sqlglot** into AST. Walk tree: allow only `SELECT` (and `WITH` for CTEs). **Block** `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, multi-statement batches, and suspicious functions. Reject if parse fails or forbidden node found — do not send to DB.

**Compare:**

> Regex on keywords = bypassed by comments or casing. AST = structural check. Still combine with read-only user.

**Follow-up:**

1. **Example bypass?**  
   **Say this:** `SELECT; DROP TABLE users` — block multi-statement. `SELECT * FROM pg_sleep(100)` — block dangerous functions via allowlist.

---

### Q7. Block DROP / DELETE — enough?

**Say this:**

> Blocking destructive statements is necessary not sufficient. Also block **cartesian joins** without WHERE on huge tables, **SELECT *** on wide tables, subqueries that explode rows. Enforce **LIMIT** injection if model omitted it (e.g. append `LIMIT 100`). Query **timeout** 5s at driver.

**Follow-up:**

1. **Resource exhaustion?**  
   **Say this:** Connection pool caps, per-user rate limits, row limit on result set before sending to LLM for summarization.

---

### Q8. Self-correction loop — how?

**Say this:**

> Execute SQL; on `DatabaseError`, append error to chat ("column `user_id` does not exist") and ask model to fix. LangGraph loop: `generate → validate → execute → if error → generate`. Increases accuracy significantly — model fixes typos and wrong joins when it sees real DB feedback.

**Compare:**

> One-shot = ~70–80% on hard schemas. With correction loop = 90%+ on many benchmarks — at cost of extra LLM calls.

**Follow-up:**

1. **VoXgent parallel?**  
   **Say this:** Same pattern as retrieve-retry in RAG graph — feedback loop with cap.

---

### Q9. Max retries on self-correction?

**Say this:**

> Cap at **2–3** attempts total. Log each failure. After cap, return user-friendly "could not translate question" — optionally show sanitized error to power users. Never infinite loop — each retry doubles cost and latency.

**Follow-up:**

1. **Same error twice?**  
   **Say this:** Stop early — model stuck; suggest rephrase or human analyst.

---

### Q10. Row limits and result size?

**Say this:**

> Force `LIMIT 100` (or 1000) on every query. Truncate wide results before passing back to LLM for natural language summary. Large result sets → ask user to narrow question. Protect DB and token budget.

**Follow-up:**

1. **Aggregate queries?**  
   **Say this:** `GROUP BY` may return few rows — still limit; `COUNT(*)` on billion rows needs timeout not row limit.

---

## C. Production & use cases

### Q11. VoXgent / Europa style use cases?

**Say this:**

> **Europa-style:** Marketing ops asks "which campaigns had connect rate below 10% last week?" over MySQL/Postgres analytics — text-to-SQL on read replica. **VoXgent-style:** Internal dashboard for call volume by tenant, average handle time, RAG hit rate — not customer-facing voice path. Voice stays RAG + tools; SQL for **back-office metrics**.

**Compare:**

> Customer voice = low latency, no SQL generation mid-call. Analyst chat = 5–15s OK for SQL loop.

**Follow-up:**

1. **Why not SQL on live call?**  
   **Say this:** Latency, error rate, and security — wrong SQL on voice is bad UX; pre-built APIs or tools safer.

---

### Q12. When NOT to use text-to-SQL?

**Say this:**

> **Do not use** when: data is mostly unstructured (use RAG); queries need complex business logic better as saved reports; schema is huge and ambiguous without curated semantic layer; users need guaranteed correct financial numbers (use certified Looker/Tableau); or write operations required (use APIs not LLM SQL).

**Compare:**

> Text-to-SQL = flexible ad-hoc. Certified BI = governed metrics. Pick governance over flexibility for board-level numbers.

**Follow-up:**

1. **Semantic layer alternative?**  
   **Say this:** dbt metrics + natural language maps to **named metrics** not raw tables — fewer hallucinations.

---

### Q13. Multi-tenant SQL isolation?

**Say this:**

> Every generated query must include **tenant_id filter** from auth token — inject in prompt as hard rule and **validate in AST** or post-process wrapper that adds `WHERE tenant_id = :tid`. Never trust model to remember tenant from question text.

**Follow-up:**

1. **VoXgent parallel?**  
   **Say this:** Same as Pinecone metadata filter — tenant from JWT, not prompt.

---

### Q14. LangGraph for text-to-SQL?

**Say this:**

> Nodes: `prune_schema → generate_sql → ast_validate → execute → [error → correct_sql]* → summarize_results → end`. State holds `question`, `schema_chunk`, `sql`, `errors`, `rows`. Clear edges and max loop count — easier to test than hidden while-loop.

**Follow-up:**

1. **Checkpointing?**  
   **Say this:** Useful for async long queries or human approval before running expensive SQL.

---

### Q15. Explain results to user — second LLM call?

**Say this:**

> After safe execution, pass **small** result table to LLM: "Summarize for business user, do not invent numbers." Structured output optional: `{ summary, row_count, caveats }`. Numbers in summary must match result JSON — validate or template from data without LLM for critical metrics.

**Compare:**

> LLM summary = readable. Template summary = safer for finance — "Returned 42 rows, top customer Acme Corp."

---

### Q16. Column name hallucination — prevention?

**Say this:**

> Pruned schema with exact names, few-shots using real columns, self-correction from DB errors. Optional fuzzy match suggestion in executor: "did you mean `customer_id`?" in retry prompt.

---

### Q17. Eval for text-to-SQL?

**Say this:**

> Golden set: question → expected SQL or expected result rows. Metrics: **execution accuracy** (runs without error), **result accuracy** (matches gold), **valid efficiency**. Run in CI against test DB with synthetic schema. Track regression when changing model or prompt.

**Follow-up:**

1. **Spider / BIRD benchmarks?**  
   **Say this:** Know them for interviews; your prod eval needs **your** schema and typos users actually type.

---

### Q18. Few-shot examples — static or dynamic?

**Say this:**

> **Dynamic** — embed past successful question-SQL pairs, retrieve top 3 similar for current question. Better than static examples for domain jargon. Curate gold pairs from analyst-approved queries.

**Compare:**

> Static few-shots in prompt for bootstrapping; vector few-shots for scale.

---

### Q19. Query timeout and connection pooling?

**Say this:**

> `statement_timeout=5000ms` on Postgres, pool size limits, cancel long queries. Log slow SQL for index tuning. LLM often omits filters — timeout prevents hung connections.

---

### Q20. Master compare — text-to-SQL safety stack (30 seconds)

**Say this:**

> "Text-to-SQL in production is a read-only replica, sqlglot AST allowing only SELECT, forced LIMIT, 5-second timeout, tenant filter from auth, and a LangGraph self-correction loop capped at two retries. Schema comes from dynamic pruning with FK expansion, not the whole database. I use it for Europa-style ops analytics, not VoXgent live voice — different latency and risk profile."

---

**Related:** [Artifact lesson 3](../Artifacts/lesson_3_text_to_sql.md) · `examples/lesson_3_text_to_sql/` · [04 MCP & Agents](./04_MCP_Tools_Agentic_AI_QA.md) · [07 Eval & Guardrails](./07_Evaluation_Guardrails_Production_QA.md) · Infosys [02 RAG](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) (when RAG not SQL)
