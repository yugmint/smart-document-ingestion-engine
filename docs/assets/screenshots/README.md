# Screenshots

Empty for now — this project is a CLI + backend API with no UI. If you add
screenshots later, good candidates:

- A terminal capture of `python -m src.ingestion.pipeline file.pdf` output.
- The FastAPI auto-generated docs UI at `http://localhost:8000/docs` (once
  `uvicorn src.ingestion.api:app` is running) showing the `/ingest` endpoint.
- `scripts/validate_chunks.py --dump-samples 5` output on a real document.
