import argparse
import os
import sys
import time
import re
from typing import List, Tuple
from transformers import pipeline, set_seed
import sqlparse

DEFAULT_MODEL = os.environ.get("TINY_SQL_MODEL", "bigscience/bloom-3b")

SCHEMA = {
    "Users": ["user_id", "name", "email"],
    "Orders": ["order_id", "user_id", "product_id", "quantity", "order_date"],
    "Products": ["product_id", "name", "price"]
}

ALLOWED_TABLES = {t.lower() for t in SCHEMA.keys()}

# Forbidden SQL keywords
FORBIDDEN_WORDS = {"drop", "delete", "truncate", "update", "insert", "alter", "create", "grant", "revoke"}

# ---------- Prompt template (few-shot) ----------
BASE_PROMPT = """
You are an SQL generator assistant. Use ONLY the schema below and produce RAW SQL as the only output (no explanation).

Schema:
TABLE Users(user_id, name, email)
TABLE Orders(order_id, user_id, product_id, quantity, order_date)
TABLE Products(product_id, name, price)

Rules:
1) Output ONLY valid SQL (single statement) and nothing else.
2) Use JOINs when necessary to combine tables.
3) Do NOT use forbidden commands: DROP, DELETE, TRUNCATE, UPDATE, INSERT, ALTER, CREATE.
4) Always use table names exactly as in the schema (Users, Orders, Products).
5) Keep queries concise and produce valid SQL statements ending with a semicolon.

Examples:
Q: List all users who placed an order.
A: SELECT u.name, u.email
   FROM Users u
   JOIN Orders o ON u.user_id = o.user_id;

Q: Show order id, user name and product name for all orders.
A: SELECT o.order_id, u.name AS user_name, p.name AS product_name
   FROM Orders o
   JOIN Users u ON o.user_id = u.user_id
   JOIN Products p ON o.product_id = p.product_id;

Q: What are the top 5 most expensive products?
A: SELECT name, price
   FROM Products
   ORDER BY price DESC
   LIMIT 5;

Now generate SQL for the question below. Output ONLY the SQL statement.

QUESTION:
{question}

PREVIOUS_SQL:
{previous_sql}

ERROR_HINT:
{error_hint}
"""



# ---------- logging to stderr so stdout remains pure SQL ----------
def log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


# ---------- Validation functions ----------
def parentheses_match(s: str) -> bool:
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                return False
            stack.pop()
    return not stack

def quotes_match(s: str) -> bool:
    # counts of single and double quotes must be even
    return s.count("'") % 2 == 0 and s.count('"') % 2 == 0

def contains_forbidden(sql: str) -> List[str]:
    found = []
    low = sql.lower()
    for kw in FORBIDDEN_WORDS:
        # catch whole word matches
        if re.search(r"\b" + re.escape(kw) + r"\b", low):
            found.append(kw)
    return found

def has_select_from(sql: str) -> bool:
    low = sql.lower()
    return ("select" in low) and ("from" in low)

def uses_known_tables(sql: str) -> Tuple[bool, List[str]]:
    """Return (ok, used_tables_list) - warn if unknown tables are referenced"""
    low = sql.lower()
    used = []
    for t in ALLOWED_TABLES:
        if re.search(r"\b" + re.escape(t) + r"\b", low):
            used.append(t)

    return (len(used) > 0, used)

def basic_sqlparse_ok(sql: str) -> bool:
    try:
        parsed = sqlparse.parse(sql)
        if not parsed:
            return False
        # Require statement is a SELECT
        stmt = parsed[0]
        first_token = stmt.token_first(skip_cm=True)
        if first_token is None:
            return False
        # token type name may not be exact; simply check the normalized text starts with SELECT
        normalized = stmt.normalized.strip().lower()
        return normalized.startswith("select")
    except Exception:
        return False

def validate_sql(sql: str) -> Tuple[bool, List[str]]:
    """Return (is_valid, list_of_error_messages)."""
    errors = []
    trimmed = sql.strip()
    if not trimmed:
        errors.append("Empty SQL.")
        return False, errors

    # avoid multiple semicolons that could indicate multiple statements
    if trimmed.count(";") > 1:
        errors.append("Multiple statements detected (more than 1 semicolon).")
    # Require final semicolon
    if not trimmed.endswith(";"):
        errors.append("SQL should end with a semicolon ';'.")

    if not parentheses_match(trimmed):
        errors.append("Mismatched parentheses/brackets.")
    if not quotes_match(trimmed):
        errors.append("Mismatched quotes.")
    forb = contains_forbidden(trimmed)
    if forb:
        errors.append(f"Forbidden keyword(s) present: {', '.join(forb)}")

    if not has_select_from(trimmed):
        errors.append("Missing SELECT and/or FROM clause.")

    known, used_tables = uses_known_tables(trimmed)
    if not known:
        errors.append("No known schema tables referenced (Users, Orders, Products).")
    else:
        pass

    if not basic_sqlparse_ok(trimmed):
        errors.append("sqlparse could not detect a valid SELECT statement (parsing error).")

    return (len(errors) == 0, errors)


# ---------- Model generation wrapper ----------
def make_generator(model_name: str, seed: int = 42):
    log(f"Loading model '{model_name}' (this may take a while)...")
    set_seed(seed)
    try:
        gen = pipeline(
            "text-generation",
            model=model_name,
            tokenizer=model_name,
        )
        return gen
    except Exception as e:
        log("Failed to load model with device_map=auto. Trying without device_map...")
        try:
            gen = pipeline("text-generation", model=model_name, tokenizer=model_name)
            return gen
        except Exception as e2:
            log("Model loading failed:", e2)
            raise e2


def generate_sql_from_model(gen, prompt: str, max_new_tokens: int = 256, temperature: float = 0.0) -> str:
    """Call the HF text-generation pipeline. Return raw text produced by model."""
    # Use deterministic generation (temperature=0) to improve reproducibility by default
    out = gen(
        prompt,
        max_new_tokens=max_new_tokens,
        do_sample=(temperature > 0.0),
        temperature=temperature,
        top_k=50,
        top_p=0.95,
        eos_token_id=None,
        return_full_text=False
    )
    # Pipeline returns list of dicts. Join 'generated_text' if multiple.
    if isinstance(out, list) and out:
        text = out[0].get("generated_text", "")
    else:
        text = str(out)
    return text.strip()


# ---------- Main flow ----------
def run(question: str, model_name: str, max_retries: int = 3, temperature: float = 0.0):
    # Create generator
    gen = make_generator(model_name)

    previous_sql = ""
    error_hint = ""
    final_sql = None

    for attempt in range(1, max_retries + 1):
        prompt = BASE_PROMPT.format(question=question, previous_sql=previous_sql, error_hint=error_hint)
        log(f"\n=== Attempt {attempt} ===")
        log("Prompt (first 400 chars):")
        log(prompt[:400] + ("..." if len(prompt) > 400 else ""))
        try:
            candidate = generate_sql_from_model(gen, prompt, temperature=temperature)
        except Exception as e:
            log("Model generation failed:", e)
            candidate = ""
            
        # Attempt to extract the first semicolon-terminated statement
        sql_match = re.search(r"(?s)(select\b.*?;)", candidate, flags=re.IGNORECASE)
        if sql_match:
            candidate_sql = sql_match.group(1).strip()
        else:
            candidate_sql = candidate.strip().splitlines()
            candidate_sql = " ".join(line.strip() for line in candidate_sql if line.strip())
            if not candidate_sql.endswith(";"):
                candidate_sql = candidate_sql + ";"

        #Convert to string to avoid "'tuple' has no attribute 'lower'" validation bug
        candidate_sql = str(candidate_sql)

        log("Candidate SQL (first 300 chars):")
        log(candidate_sql[:300] + ("..." if len(candidate_sql) > 300 else ""))
        ok, errors = validate_sql(candidate_sql)
        if ok:
            log("Validation: PASSED")
            final_sql = candidate_sql
            break
        else:
            log("Validation: FAILED with errors:")
            for e in errors:
                log(" -", e)
            # prepare for retry: set previous_sql and accumulate an error hint
            previous_sql = candidate_sql
            error_hint = " | ".join(errors)
            # Sleep briefly before retry to avoid overloading if running on HF inference infra
            time.sleep(0.5)
    # End loop

    if final_sql is None:
        log("\nAll attempts exhausted. Returning last candidate (may be invalid).")
        # Use last candidate_sql even if invalid, but this is the best effort.
        final_sql = previous_sql or ""

    #print ONLY the SQL query to STDOUT
    final_match = re.search(r"(?s)(select\b.*?;)", final_sql, flags=re.IGNORECASE)
    if final_match:
        output_sql = final_match.group(1).strip()
    else:
        output_sql = final_sql.strip()
        # ensure ends with semicolon
        if output_sql and not output_sql.endswith(";"):
            output_sql += ";"

    # Print final SQL 
    print(output_sql)
    # provide a final status log to stderr
    log("\n=== Summary ===")
    log("Question:", question)
    log("Model:", model_name)
    log("Attempts:", attempt if final_sql else max_retries)
    log("Final SQL (stdout):")
    log(output_sql)
    if not validate_sql(output_sql)[0]:
        log("Warning: final SQL did not pass all validation checks.")

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Tiny SQL Expert - English to SQL with small LLM + validation loop")
    p.add_argument("question", type=str, help="English question to convert to SQL (wrap in quotes)")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Hugging Face model name (must be <4B ideally)")
    p.add_argument("--retries", type=int, default=3, help="Number of correction retries")
    p.add_argument("--temp", type=float, default=0.0, help="generation temperature (0.0 deterministic)")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        run(args.question, model_name=args.model, max_retries=args.retries, temperature=args.temp)
    except Exception as ex:
        log("Fatal error:", ex)

        sys.exit(1)
