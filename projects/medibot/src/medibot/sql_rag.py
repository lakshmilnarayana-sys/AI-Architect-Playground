"""SQL RAG over mediassist.db — a plain Python function with three explicit
steps: NL -> SQL via LLM, clean the raw output to bare SQL, execute and have
the LLM phrase the result as a natural language answer.

Available only to `billing_executive` and `admin` (enforced by the caller).
"""

import re
import sqlite3

from medibot.config import DB_PATH
from medibot.llm import complete

SCHEMA = """
Table: claims
  claim_id TEXT PRIMARY KEY        -- e.g. 'CLM-2024-1000'
  patient_id TEXT, patient_name TEXT
  department TEXT                  -- e.g. 'cardiology', 'neurology', 'nephrology'
  claim_type TEXT                  -- 'cashless' or 'reimbursement'
  diagnosis_code TEXT              -- ICD code, e.g. 'I21.4'
  insurer TEXT                     -- e.g. 'Bajaj Allianz', 'New India Assurance'
  claimed_amount REAL, approved_amount REAL
  status TEXT                      -- e.g. 'pending', 'approved', 'rejected', 'escalated'
  submitted_date TEXT, resolved_date TEXT   -- ISO dates 'YYYY-MM-DD'

Table: maintenance_tickets
  ticket_id TEXT PRIMARY KEY       -- e.g. 'TKT-2024-2000'
  equipment_name TEXT, equipment_id TEXT
  category TEXT                    -- e.g. 'sterilisation', 'infusion', 'imaging'
  campus TEXT
  issue_type TEXT                  -- e.g. 'preventive_maintenance', 'sensor_failure'
  fault_code TEXT, raised_by TEXT
  raised_date TEXT, resolved_date TEXT      -- ISO dates 'YYYY-MM-DD'
  status TEXT                      -- e.g. 'open', 'in_progress', 'resolved'
  resolution_note TEXT
"""

SQL_SYSTEM = f"""You are an expert SQLite analyst for MediAssist Health Network.
Translate the user's question into a single read-only SQLite SELECT query.

Database schema:
{SCHEMA}

Rules:
- Return ONLY the SQL statement. No explanation, no markdown.
- Use exact lowercase values for status/category/claim_type columns as shown in the schema.
- Dates are TEXT in 'YYYY-MM-DD'; use strftime/date functions for date math.
"""

ANSWER_SYSTEM = """You are MediBot, an internal analytics assistant for MediAssist
Health Network. Given a question, the SQL that was run, and the raw result rows,
answer the question concisely in natural language. Include the key numbers.
If the result is empty, say no matching records were found."""


def _clean_sql(raw: str) -> str:
    """Extract the bare SQL statement from raw LLM output (strip code fences,
    leading prose, trailing chatter)."""
    text = raw.strip()
    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    match = re.search(r"(SELECT\b.*?)(?:;|$)", text, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError(f"No SELECT statement found in LLM output: {raw!r}")
    return match.group(1).strip()


def _execute(sql: str) -> tuple[list[str], list[tuple]]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchmany(50)
        return columns, rows
    finally:
        conn.close()


def sql_rag_chain(question: str) -> str:
    """Three explicit steps: generate SQL, clean it, execute + summarise."""
    # Step 1: natural language -> SQL via LLM
    raw_sql = complete(SQL_SYSTEM, question)

    # Step 2: clean the raw LLM output down to the bare SQL statement
    sql = _clean_sql(raw_sql)

    # Step 3: execute against the database, then LLM phrases the answer
    columns, rows = _execute(sql)
    result_block = f"Columns: {columns}\nRows: {rows}"
    answer = complete(
        ANSWER_SYSTEM,
        f"Question: {question}\n\nSQL executed:\n{sql}\n\nResult:\n{result_block}",
    )
    return answer


def sql_rag_chain_verbose(question: str) -> dict:
    """Same chain, but returns the intermediate SQL for display in the UI."""
    raw_sql = complete(SQL_SYSTEM, question)
    sql = _clean_sql(raw_sql)
    columns, rows = _execute(sql)
    answer = complete(
        ANSWER_SYSTEM,
        f"Question: {question}\n\nSQL executed:\n{sql}\n\nResult:\nColumns: {columns}\nRows: {rows}",
    )
    return {"answer": answer, "sql": sql, "columns": columns, "rows": rows}
