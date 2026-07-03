# Capability: Local Code-Execution Sandbox

## What It Does
Executes LLM-generated pandas code locally against the full DataFrame in a restricted namespace with no filesystem/network/import access, capturing a designated `result`, stdout, and any error.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| code | str (Python) | `generate_code` node | yes |
| df | pandas DataFrame | loaded from `datasets.filepath` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| result | any | `AgentState.execution_result` |
| result_repr | str (truncated) | `AgentState.execution_result_repr` → answer prompt |
| stdout | str | `AgentState.execution_stdout` |
| error | str \| null | `AgentState.execution_error` → retry loop |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Python `exec` (restricted) | run code in curated namespace | capture exception → `execution_error` |

## Business Rules
- **Namespace:** globals expose only `pd`, `np`, `df`, and a curated `__builtins__` allow-list (`len`, `range`, `min`, `max`, `sum`, `sorted`, `abs`, `round`, `enumerate`, `zip`, `list`, `dict`, `set`, `tuple`, `str`, `int`, `float`, `bool`, `print`).
- **Forbidden:** `open`, `eval`, `exec`, `compile`, `__import__`, `input`, `getattr`/`setattr` escapes — so no imports, no file, no network, no subprocess.
- Code must assign its answer to a `result` variable; the sandbox reads `result` after execution.
- `print()` output is captured via redirected stdout and returned as `stdout`.
- **Timeout:** wall-clock limit (default 15s, `AGENT_SANDBOX_TIMEOUT_SECONDS`) via a worker thread; on timeout return a timeout error.
- The sandbox never raises out — every outcome is a structured `{ok, result, result_repr, stdout, error}`.

## Error Cases
- Runtime error (KeyError, TypeError, etc.) → captured type+message+trimmed traceback in `error`; fed back to `generate_code` for a bounded retry.
- Missing `result` variable → error "code did not assign `result`" → retry.
- Timeout → error "execution timed out" → retry (or failure answer if exhausted).
- Attempted forbidden operation → NameError (name unavailable) captured as error.

## Success Criteria
- [ ] Valid `result = df.groupby(...).sum()` returns `ok=True` with the correct value and its `result_repr`.
- [ ] `open('x')`, `import os`, and `__import__('os')` all fail inside the sandbox (name unavailable / not allowed) and are captured as errors, not executed.
- [ ] A raised exception is captured in `error` and does not crash the process.
- [ ] Code that omits `result` yields a clear "no result" error.
- [ ] An infinite/long loop is stopped at the timeout and returns a timeout error.
