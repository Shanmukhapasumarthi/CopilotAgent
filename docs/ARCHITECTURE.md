# Architecture

```text
Streamlit UI / CLI
        │
        ▼
 LangGraph (AgentState)
        │
        ├── Task analyzer ──▶ Planner
        │
        └── Router (LLM optional; Python constraints always)
                │
                ├── WRITE_CODE / MODIFY_CODE
                ├── WRITE_TESTS
                ├── RUN_TESTS ──▶ Docker pytest sandbox
                ├── INSPECT_ERROR
                ├── VERIFY (Python, not the LLM)
                └── FINISH / FAIL
```

Control objects (`TaskAnalysis`, `Plan`, `AgentDecision`, `ErrorAnalysis`, `VerificationResult`) are Pydantic models. Unknown router actions are rejected.

Python policy (`heuristic_decision` + `constrain_decision`) can run the loop without an LLM in tests. Live runs still use Groq for generation.

See `docs/SECURITY.md` for the execution boundary.
