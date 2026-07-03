from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Identity / input
    run_id: str                     # message id for this ask; set at init
    session_id: str                 # set at init
    dataset_id: str                 # set at init
    question: str                   # set at init (user's NL question)

    # Loaded resources (privacy boundary lives in load_context)
    filepath: str                   # local path to the raw CSV (init)
    dataframe: Any                  # the full pandas DataFrame (load_context)
    schema: dict                    # {column: dtype, ...}
    sample: list                    # first N rows (default 5) as records
    profile: dict                   # aggregate stats (missing %, ranges) + sample
    messages: list                  # prior chat turns — [] in P1

    # Planning
    plan: str
    needs_clarification: bool
    clarify_question: str | None

    # Code gen + execution
    generated_code: str
    execution_result: Any
    execution_result_repr: str
    execution_stdout: str
    execution_error: str | None
    retry_count: int
    max_retries: int

    # Output
    answer: str
    steps: list                     # [{step, label, status}]
    error: str | None
    table: dict | None              # structured result table {columns, rows, row_count, truncated}

    # Cost (accumulated across all Gemini calls)
    input_tokens: int
    output_tokens: int
    cost_usd: float
