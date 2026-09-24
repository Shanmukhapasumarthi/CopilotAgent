# Limitations

- **No live benchmark scores in this repo** until `python -m evaluation.evaluate` is run with Groq and Docker.
- Groq structured output can still fail schema validation; the provider retries once, then the node records an error.
- The agent's own tests can be too weak or too coupled. Hidden evaluation tests are the independent check.
- `MODIFY_CODE` rewrites the whole module; it does not do surgical patches.
- File tasks are path-string problems. The sandbox is read-only and has no host files.
- Windows requires Docker Desktop running; `docker` on PATH is not enough.
- Streamlit live updates wait on each graph node; long Groq + Docker runs will block the UI until a node finishes.
- There is no multi-user auth, persistence, or queue.
