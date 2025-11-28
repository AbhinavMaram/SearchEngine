from fastapi import FastAPI, Query, HTTPException
import os
from pydantic import BaseModel
from typing import Any, List
import uvicorn
from contextlib import asynccontextmanager
import asyncio
import logging

from search_engine import SearchEngine
from data_loader import DataLoader


class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: List[Any]


loader = DataLoader(refresh_interval=300)  # refresh every 5 minutes (optional)
engine = SearchEngine()


logger = logging.getLogger("simple-search")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        try:
            # run the blocking loader in a thread to avoid blocking the event loop
            docs = await asyncio.to_thread(loader.load)
            engine.build_index(docs, id_field="id")
            logger.info("Loaded %d documents into index", len(engine.docs))
            loader.start_periodic()
        except Exception:
            # if remote API not available at startup, log the error so we can debug
            logger.exception("Failed to load messages at startup")
        yield
    finally:
        # Shutdown: stop background loader
        await asyncio.to_thread(loader.stop)


app = FastAPI(title="Search Service", lifespan=lifespan)


@app.get("/search", response_model=SearchResponse)
def search(search_query: str = Query(..., min_length=1, title="Search Query", description="Search by id, name, message"), page: int = 1, page_size: int = 10):
    # validate params
    max_page_size = int(os.getenv("MAX_PAGE_SIZE", "100"))
    if page < 1 or page_size < 1 or page_size > max_page_size:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pagination parameters: page must be >=1 and page_size must be between 1 and {max_page_size}",
        )
    total, results = engine.search(search_query, page=page, page_size=page_size)
    return SearchResponse(total=total, page=page, page_size=page_size, results=results)


@app.get("/health")
def health():
    return {"status": "ok", "indexed_docs": len(engine.docs)}



if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level="info")
