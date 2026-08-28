# Lesson 3: Text-to-SQL (Siemens Interview Mode)

This document provides a detailed breakdown of building a production-grade **Text-to-SQL (Natural Language to SQL)** system. We analyze how databases (MySQL, PostgreSQL) connect to an LLM, how natural language queries are translated into database-specific SQL, and the architectural guardrails necessary to run this safely and efficiently in enterprise environments.

---

## 1. Conceptual Breakdown of Concepts

### A. Schema Context Injection & DDL Generation
*   **Why**: An LLM cannot query a database without knowing the tables, column names, data types, and relationships (foreign keys).
*   **What**: Data Definition Language (DDL) is the SQL statements (like `CREATE TABLE`) that define the schema. We extract this DDL and inject it into the LLM system prompt.
*   **Where**: Generated dynamically by the application layer using database metadata engines (e.g., SQLAlchemy Inspector) and sent as context in the prompt payload.
*   **How**: Programmatically inspect database tables, format the `CREATE TABLE` structures, add sample rows (first 3 rows) to show data formatting, and format relationships.
*   **Production Considerations**: Large databases with hundreds of tables will exceed context limits if you inject the entire schema. You must prune the schema to only include relevant tables.
*   **Interview Explanation (30 seconds)**: *"To enable an LLM to write SQL, we must inject database metadata—specifically the DDL—into the system prompt. However, pure DDL lacks context. We augment it by appending database comments (table/column descriptions), column types, foreign key relationships, and a few sample rows. This gives the LLM the exact syntactic and semantic mapping of the database structure."*
*   **Common Mistakes**: Injecting the entire database schema for every query, which inflates token usage, increases API latency, and confuses the model (known as the "lost in the middle" attention problem).

### B. Dynamic Schema Pruning (Semantic Retrieval)
*   **Why**: In enterprise systems with 100+ tables, injecting all DDL exceeds the context window and degrades translation quality.
*   **What**: Retrieving only the subset of tables and columns relevant to the user's natural language query.
*   **Where**: Calculated in the application layer using a semantic vector search or a keyword index before the LLM generation step.
*   **How**: Store table DDLs, comments, and column definitions as documents. Embed them and store them in a vector database. When a query arrives (e.g., *"How many items did customer X buy?"*), retrieve the top $K$ (e.g., 5-10) most similar table schemas and inject only those.
*   **Production Considerations**: Hard dependencies (like foreign keys) must be preserved. If table `orders` is retrieved, table `customers` must also be pulled in if the query references attributes of both, even if `customers` had a slightly lower similarity score.
*   **Interview Explanation (30 seconds)**: *"For large schemas, we implement dynamic schema pruning. We create a vector index of our table schemas (metadata, table descriptions, column names). We embed the user's natural language query, run a similarity search against the table index, and retrieve only the relevant schemas. We also run a dependency check to ensure any foreign key relationships between the selected tables are included."*
*   **Common Mistakes**: Relying strictly on vector search similarity, which might miss a parent lookup table (e.g., retrieving `orders` but missing `users`), causing SQL generation to fail on missing table joins.

### C. Dialect-Specific Prompting & Few-Shot Examples
*   **Why**: Different SQL databases use different dialects (e.g., PostgreSQL uses `LIMIT`, Oracle uses `ROWNUM`, MySQL uses backticks, PostgreSQL uses double quotes for identifiers).
*   **What**: Providing the LLM with specific instructions on the target database engine, alongside concrete natural-language-to-SQL pairs (Few-Shot Prompting).
*   **Where**: Embedded in the system instructions and system messages.
*   **How**: System prompt: *"You are a PostgreSQL expert. Use PG-compatible SQL only..."* and supply 3-5 hardcoded pairs of `User Query` and `Target SQL` representing complex joins or calculations.
*   **Production Considerations**: Select few-shot examples dynamically. Use semantic search to find past query-SQL pairs that are semantically similar to the user's current query and inject them as few-shots.
*   **Interview Explanation (30 seconds)**: *"LLMs perform significantly better when instructed on the exact SQL dialect and given few-shot examples. Instead of static examples, we dynamically retrieve historical query-to-SQL pairs using vector search on user queries. This teaches the model the exact domain logic, schema nuances, and syntax required for the current request."*
*   **Common Mistakes**: Using generic SQL instructions that result in PostgreSQL-specific functions (like `DATE_TRUNC`) being executed on a MySQL database, throwing runtime database errors.

### D. SQL Execution Guardrails & Sandboxing
*   **Why**: Executing raw LLM-generated code on a production database is a massive security risk (SQL Injection, destructive `DROP TABLE` commands, or resource-heavy infinite loops).
*   **What**: Protective layers that analyze, validate, and restrict generated SQL before it touches the database.
*   **Where**: Operates inside the application gateway between the LLM output parser and database execution.
*   **How**: 
    1.  Use a **Read-Only Database Replica** with limited user privileges.
    2.  Set strict query execution timeouts (e.g., 5 seconds).
    3.  Analyze the SQL using an Abstract Syntax Tree (AST) parser (e.g., `sqlglot` or `sqlparse`) to verify it only contains `SELECT` statements and blocks destructive keywords.
*   **Production Considerations**: Always configure connection pooling with strict resource limits. A poorly written query like `SELECT * FROM logs JOIN orders` without filters can lock the database and crash the server.
*   **Interview Explanation (30 seconds)**: *"Security is the primary bottleneck for production Text-to-SQL. We address this using a defense-in-depth approach: First, the LLM connects exclusively to a read-only database replica. Second, we parse the generated SQL string using an AST parser like `sqlglot` to verify it only contains safe SELECT nodes. Lastly, we enforce strict query execution timeouts and row limits (e.g., LIMIT 100) at the driver level."*
*   **Common Mistakes**: Running the database connection as a root/admin user, or relying on prompt engineering alone (e.g., *"Do not write drop table queries"*) to prevent SQL injection or destructive operations.

### E. Self-Correction & Execution Feedback Loop
*   **Why**: LLMs occasionally make syntax mistakes, hallucinate column names, or use incorrect join columns.
*   **What**: An agentic loop where database execution errors are fed back to the LLM to write a corrected query.
*   **Where**: Managed inside a stateful orchestrator (like LangGraph or a Python loop).
*   **How**: If database execution throws a `DatabaseError` (e.g., *"column 'user_id' does not exist"*), catch the exception, format it, append it to the chat history, and prompt the LLM: *"The previous query failed with error: {error}. Please correct the query."*
*   **Production Considerations**: Limit the correction loop to a maximum of 2-3 retries to avoid infinite loops and high API costs.
*   **Interview Explanation (30 seconds)**: *"When a generated SQL query fails execution, we run a self-correction loop. We capture the raw database error message, inject it back into the model's history, and ask it to debug and regenerate the SQL. This simple feedback loop increases SQL generation accuracy from ~75% to over 92% in production environments."*
*   **Common Mistakes**: Immediately bubbling up database syntax errors to the user, causing a poor experience, rather than attempting automated self-correction.

---

## 2. The Business Problem

Enterprise data is locked inside relational databases. Historically, accessing this data required:
1.  **Engineering Bottlenecks**: Non-technical teams (marketing, operations) had to submit tickets to data analysts, taking days to get basic reports.
2.  **Rigid Dashboards**: BI tools (Tableau, Looker) provide pre-built dashboards, but cannot answer ad-hoc, multi-dimensional questions like: *"Which customer segments had the highest drop-off rate after buying product X last month?"*
3.  **Low Data Literacy**: Business users do not know SQL, and translating business questions to exact SQL queries is prone to communication gaps.

**Text-to-SQL** solves this by converting natural language requests directly to executable queries, returning immediate answers.

---

## 3. System Architecture

Below is the workflow of a secure, production-grade Text-to-SQL system:

```
                            TEXT-TO-SQL ARCHITECTURE
                            
  +------------+                   1. User Query                 +-------------------+
  | User / App | ----------------------------------------------> |   FastAPI Router  |
  +------------+                                                 +-------------------+
        ^                                                                  |
        | 9. Formatted Answer                                              | 2. Fetch Relevant
        |                                                                  v    Schema (DDL)
  +------------------+     8. Natural Language Response    +------------------------------+
  |  LLM Text        | <---------------------------------- |   Vector DB / Table Index    |
  |  Response Gen    |                                     |  (Retrieve Top-K Table DDLs) |
  +------------------+                                     +------------------------------+
        ^                                                                  |
        | 7. Rows & Data                                                   | 3. Query + Selected DDL
        |    (JSON format)                                                 v
  +------------------+                                     +------------------------------+
  | PostgreSQL/MySQL |                                     |   Prompt Builder             |
  |  Read-Replica    |                                     |  (Injects System, Schema,    |
  +------------------+                                     |   Dialect Rules & Few-Shots) |
        ^                                                  +------------------------------+
        |                                                                  |
        | 6. Execute SQL (ReadOnly)                                        | 4. Prompt Payload
        v                                                                  v
  +------------------+     5. Validated SQL Query (String) +------------------------------+
  | SQL Guardrails   | <---------------------------------- |   LLM Generator              |
  | (AST, Read-Only) |                                     |   (Produces Raw SQL)         |
  +------------------+     --------------------------------+------------------------------+
        |                                                                  ^
        +------------------- 5a. Database Syntax Error --------------------+
                            (Trigger Self-Correction Loop)
```

### Data Flow Breakdown
1.  **Query & Pruning**: The user asks: *"How many orders did we get from users in New York?"*. The application queries a vector store containing table schemas to retrieve only the `orders` and `users` tables.
2.  **Context Construction**: The prompt builder constructs a system prompt containing the pruned DDL, relationship mappings, few-shot examples, and PostgreSQL-specific dialect guidelines.
3.  **SQL Generation**: The LLM processes the prompt and outputs a raw SQL query.
4.  **Security Filtering**: The application intercepts the SQL string and parses it with `sqlglot`. It checks for unauthorized clauses (`DELETE`, `INSERT`, `DROP`) and verifies schema access constraints.
5.  **Execution**: The SQL runs against a **Read-Only Replica** database.
    *   **Success**: The resulting rows (JSON format) are passed to an LLM alongside the user's original query.
    *   **Failure**: If the database returns an error, the query and error message are routed back to the LLM for correction.
6.  **Formatting**: The final LLM synthesizes the tabular data into a clean, human-readable natural language answer.

---

## 4. Code Integration Guide (Python Implementation)

Below is the conceptual layout of a manual implementation to connect a database and execute Text-to-SQL.

### Step A: Database Connection & Schema Extraction
We use SQLAlchemy to query table schemas programmatically.

```python
from sqlalchemy import create_engine, inspect
import os

# Create read-only connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ro_user:readonly@localhost:5432/mydb")
engine = create_engine(DATABASE_URL)

def get_database_schema(table_names=None):
    """
    Programmatically extracts DDL-like schema mapping.
    """
    inspector = inspect(engine)
    schema_info = []
    
    # If no tables specified, inspect all
    if not table_names:
        table_names = inspector.get_table_names()
        
    for table_name in table_names:
        ddl = f"CREATE TABLE {table_name} (\n"
        columns = inspector.get_columns(table_name)
        col_definitions = []
        for col in columns:
            col_def = f"  {col['name']} {col['type']}"
            if not col.get('nullable', True):
                col_def += " NOT NULL"
            col_definitions.append(col_def)
            
        # Extract foreign keys to show relationships
        fkeys = inspector.get_foreign_keys(table_name)
        for fk in fkeys:
            fk_def = f"  FOREIGN KEY ({','.join(fk['referred_columns'])}) REFERENCES {fk['referred_table']}({','.join(fk['referred_columns'])})"
            col_definitions.append(fk_def)
            
        ddl += ",\n".join(col_definitions) + "\n);"
        schema_info.append(ddl)
        
    return "\n\n".join(schema_info)
```

### Step B: SQL Generation & Execution with Self-Correction Loop
Below is the agentic execution flow with guardrails.

```python
import openai
import re
from sqlalchemy.sql import text
import sqlglot

client = openai.AsyncOpenAI()

async def generate_sql_query(user_query: str, schema_ddl: str, database_dialect: str = "PostgreSQL") -> str:
    """
    Calls the LLM to translate natural language into SQL.
    """
    system_prompt = f"""You are an expert {database_dialect} developer.
Given the database schema below, write a single syntacticly correct {database_dialect} query that answers the user's question.

Schema DDL:
{schema_ddl}

Rules:
1. Return ONLY the raw SQL query.
2. Do NOT wrap the query in markdown blocks (like ```sql).
3. Only use SELECT statements. Never perform writes (INSERT, UPDATE, DELETE, DROP).
4. Always apply a LIMIT of 100 rows to queries unless explicitly overridden.
"""
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        temperature=0.0 # Deterministic SQL output
    )
    return response.choices[0].message.content.strip()

def validate_sql_ast(sql_query: str) -> bool:
    """
    Uses sqlglot to parse AST and verify only SELECT queries are executed.
    """
    try:
        parsed = sqlglot.parse_one(sql_query)
        # Check if the top-level node is a SELECT expression
        if parsed.key != "select":
            return False
        
        # Walk AST to ensure no destructive actions exist
        for expression in parsed.find_all(sqlglot.exp.Command):
            return False # Disallow custom commands
            
        return True
    except Exception:
        return False # Syntax parse error

async def run_text_to_sql_pipeline(user_query: str):
    # Step 1: Get relevant database schema (dynamic pruning or full schema)
    schema_ddl = get_database_schema(table_names=["users", "orders"]) # Hardcoded table selection for simplicity
    
    max_retries = 3
    retry_count = 0
    history = [
        {"role": "system", "content": f"You are a SQL generator. Database schema:\n{schema_ddl}"},
        {"role": "user", "content": user_query}
    ]
    
    while retry_count < max_retries:
        # Generate query
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=history,
            temperature=0.0
        )
        sql_query = response.choices[0].message.content.strip()
        
        # Clean potential markdown wrapping
        sql_query = re.sub(r"```sql|```", "", sql_query).strip()
        
        # Step 2: Validate AST guardrails
        if not validate_sql_ast(sql_query):
            error_msg = "Guardrail violation: Only SELECT queries are permitted."
            history.append({"role": "assistant", "content": sql_query})
            history.append({"role": "user", "content": f"Error: {error_msg}. Rewrite the query."})
            retry_count += 1
            continue
            
        # Step 3: Execute on Read-Only Connection
        try:
            with engine.connect() as conn:
                # Set dynamic execution timeout at connection level
                conn.execute(text("SET statement_timeout = 5000")) # 5s timeout (PG specific)
                result = conn.execute(text(sql_query))
                rows = [dict(row._mapping) for row in result]
                return {"sql": sql_query, "data": rows}
                
        except Exception as db_error:
            # Capture database error and send back to LLM for self-correction
            error_message = str(db_error)
            history.append({"role": "assistant", "content": sql_query})
            history.append({"role": "user", "content": f"Database execution failed with error:\n{error_message}\nIdentify the error (e.g., typos, column name mismatches) and output a corrected SQL query."})
            retry_count += 1
            
    raise RuntimeError("Failed to generate a valid SQL query after maximum retries.")
```

---

## 5. Why Manual Implementation Fails at Scale

While the above manual Python script works for basic setups, it encounters severe production limitations:
1.  **Lack of Semantic Context**: Table names like `usr_tb` and column names like `c_dt` are unintelligible to raw LLMs. The schema needs rich semantic descriptions associated with it.
2.  **Schema Drift**: As developers run migrations to add columns or split tables, the hardcoded schemas or local indices become stale, causing generated SQL to reference non-existent columns.
3.  **Complex Joins and Fan-Out**: Standard LLMs struggle with nested subqueries, window functions (`ROW_NUMBER()`), and joining multiple tables without explicit database indices.
4.  **Connection Management Overhead**: Managing read-replica pooling, dynamic statement timeouts, and transactional rollbacks manually across multiple API routes leads to fragile, state-heavy code.

---

## 6. The LangChain Abstraction

LangChain simplifies Text-to-SQL connection and execution through modular wrappers:
*   **`SQLDatabase`**: A wrapper around SQLAlchemy that connects to any supported dialect and automatically extracts schema information.
*   **`create_sql_query_chain`**: A pre-built chain that prompts the LLM with database context and parses out the generated SQL.
*   **`QuerySQLDataBaseTool`**: An executor tool that runs the validated query and returns tabular results.

```python
from langchain_community.utilities import SQLDatabase
from langchain.chains import create_sql_query_chain
from langchain_openai import ChatOpenAI

# Initialize Database wrapper
db = SQLDatabase.from_uri("postgresql://ro_user:readonly@localhost:5432/mydb")

# Instantiate LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Create translation chain
chain = create_sql_query_chain(llm, db)

# Execute translation (returns SQL string)
sql_query = chain.invoke({"question": "How many orders were placed last week?"})
```

---

## 7. The LangGraph Solution

For production systems, a simple chain is too fragile. If the SQL has a syntax error, a chain breaks. LangGraph models the Text-to-SQL pipeline as a stateful graph that implements:
1.  **State Management**: Tracks user query, schema, generated SQL, execution results, error message, and retry counts.
2.  **Dynamic Routing**: Edges route the state based on whether the SQL is valid, needs correction, or failed completely.
3.  **Corrective Execution Node**: A node that executes the SQL and catches exceptions, feeding them back into the graph state.

```mermaid
graph TD
    Start([User Input]) --> RouteQuery[Dynamic Schema Pruning]
    RouteQuery --> GenerateSQL[Generate SQL Node]
    GenerateSQL --> ValidateSQL{AST & Guardrail Check}
    ValidateSQL -- Invalid/Unsafe --> GenerateSQL
    ValidateSQL -- Valid --> ExecuteSQL[Execute SQL Node]
    ExecuteSQL -- Database Syntax Error --> CheckRetry{Retry Count < Max}
    CheckRetry -- Yes --> GenerateSQL
    CheckRetry -- No --> Fallback[Fallback: Human Review / Safe Message]
    ExecuteSQL -- Success --> FormatResult[Synthesize Text Answer Node]
    FormatResult --> End([Output Result])
```

---

## 8. Production Considerations (Enterprise Architecture)

1.  **Strict Transaction Limits**: Set connection-level resource quotas. Always enforce a hard row limit (e.g., `LIMIT 100`) and statement execution timeout (`statement_timeout` in Postgres, `max_execution_time` in MySQL) to prevent catastrophic database locks or CPU exhaustions.
2.  **Semantic Schema Dictionary**: Instead of relying solely on SQL table metadata, maintain a schema data dictionary in a vector store. Each table document should specify the table name, user-friendly description, business logic (e.g., *"Active users are defined as status='active' AND last_login >= 30 days ago"*), and typical query examples.
3.  **Read-Only Replica Isolation**: Never run Text-to-SQL on your primary write database. Always use a dedicated read-replica. Configure the database user with minimal privileges: only `SELECT` permissions on required tables/views, and explicit access restrictions to sensitive tables containing passwords or personally identifiable information (PII).
4.  **AST Validation (Safety Net)**: A prompt instruction is not a security guarantee. Always validate the generated SQL string using a parser library like `sqlglot` to verify that the query is a pure SELECT query and does not attempt write operations or system administrative calls (like `VACUUM` or `ANALYZE`).
5.  **DDL Ingestion Cache**: Re-inspecting the database metadata via SQLAlchemy on every query adds 100-300ms of latency. Cache the DDL schema strings in Redis or in-memory, updating them only during application deployment or schema migration events.
6.  **Explain-Plan Verification**: For complex queries, execute an `EXPLAIN` plan check on the database replica before running the actual query. If the estimated cost exceeds a specific threshold (e.g., scanning over 1,000,000 rows without index hits), reject the query and prompt the user to refine their request.
