# Search Service

This repository implements a small search service on top of the provided messages API.

Features
- FastAPI-based HTTP service exposing /search and /health endpoints
- In-memory inverted-index for fast text search
- Periodic refresh from the upstream messages endpoint (configurable)
- Dockerfile for easy deployment

Quick start (local)

1. Create a virtualenv and install deps:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2. Run the server:

On Windows it's recommended to use the `py` launcher (works even if `python` isn't on PATH):

```powershell
# activate your venv first (if using one)
.\.venv\Scripts\Activate.ps1

# recommended: use the py launcher to run uvicorn
py -3 -m uvicorn main:app --port 8080
```

3. Query the API:

GET http://localhost:8080/search?search_query=your+query&page=1&page_size=10

4. GET /Search Endpoint:

GET http://localhost:8080/docs#/default/search_search_get


Design notes

Alternatives considered for the search implementation:

1. Use an external search engine (Elasticsearch/OpenSearch/Lucene).
   - Pros: full-featured (scoring, tokenization, text analysis), scales to large datasets.
   - Cons: heavier infra, network hop adds latency and operational complexity.

2. Use an embedded/packaged search library (Whoosh for Python, Lucene via PyLucene).
   - Pros: fast, feature rich, can be embedded in the app image.
   - Cons: larger dependency footprint and more code to maintain; Whoosh can be slower than optimized C++ options.

3. Use vector search (embeddings + FAISS or Annoy) for semantic queries.
   - Pros: great for semantic matching and queries beyond exact token overlap.
   - Cons: need to compute embeddings and maintain index; requires more memory & CPU and a model for embeddings.

4. Simple in-memory inverted index (this implementation).
   - Pros: extremely simple, low-latency for moderate data sizes, few dependencies.
   - Cons: not suited to huge datasets or advanced linguistic features.


How to reduce latency to ~30ms

Short summary of practical steps:

- Keep the index in-memory on the same host where the HTTP request is served to avoid an extra network hop.
- Warm the service (avoid cold starts). Use a single long-lived container/process and configure health checks to keep it ready.
- Use a compiled, optimized search library (e.g., Lucene running in a JVM or C++ engine) or a dedicated in-memory cache like Redis with precomputed search keys.
- Use an efficient tokenizer and precompute normalized fields. Avoid on-request heavy serialization or parsing.
- Scale vertically (more CPU) and horizontally behind a low-latency load balancer.
- If needed, precompute and store the top-N results for frequent queries in a fast cache (Redis, in-process LRU).

Example deployment options
- Render: push image or connect the GitHub repo and set the start command to `uvicorn main:app --host 0.0.0.0 --port 8080`.
- Google Cloud Run: build container and deploy; the service can pull the messages API directly.
- Railway / Fly / Heroku: similar approach.


Notes about deployment and performance guarantees

- This repository provides the code and a Dockerfile for running the service publicly. To actually deploy to a public URL you'll need to build and push the image to a container registry or use a platform that builds directly from source and provide any necessary credentials.
- The implementation keeps the dataset in memory so searches are typically very fast (<100ms) for modest datasets. Your mileage will vary depending on the size of the upstream messages dataset and the hosting environment.
