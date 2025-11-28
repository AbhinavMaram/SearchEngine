import re
from collections import defaultdict, Counter
from typing import Dict, List, Any, Iterable, Tuple


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    text = text.lower()
    # simple tokenization: split on non-alphanum
    tokens = re.split(r"[^a-z0-9]+", text)
    return [t for t in tokens if t]


class SearchEngine:
    """A tiny in-memory inverted-index search engine.

    - build_index(docs): docs is iterable of dicts with 'id' field
    - search(query): returns ordered list of docs
    This is intentionally simple but fast for moderate-sized datasets.
    """

    def __init__(self):
        self.index: Dict[str, set] = defaultdict(set)
        self.docs: Dict[str, Dict[str, Any]] = {}

    def build_index(self, docs: Iterable[Dict[str, Any]], id_field: str = "id") -> None:
        self.index.clear()
        self.docs.clear()
        for d in docs:
            if id_field not in d:
                # try common alternatives
                if "_id" in d:
                    doc_id = str(d["_id"])
                else:
                    continue
            else:
                doc_id = str(d[id_field])
            self.docs[doc_id] = d
            # choose fields to index: flatten values that are strings
            text_parts = []
            for v in d.values():
                if isinstance(v, str):
                    text_parts.append(v)
            full = " ".join(text_parts)
            for token in set(tokenize(full)):
                self.index[token].add(doc_id)

    def _score(self, query_tokens: List[str], doc_id: str) -> int:
        # simple score: count of query tokens present in doc
        score = 0
        for t in query_tokens:
            if doc_id in self.index.get(t, ()):  # type: ignore
                score += 1
        return score

    def search(self, query: str, page: int = 1, page_size: int = 10) -> Tuple[int, List[Dict[str, Any]]]:
        """Search and return (total_hits, list_of_docs)."""
        # If the query looks like a UUID, prefer exact id/user_id matches to avoid token collisions
        uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        if uuid_re.match(query.strip()):
            q = query.strip()
            matches = []
            for doc_id, doc in self.docs.items():
                # exact match on id or user_id
                if str(doc.get("id")) == q or str(doc.get("user_id")) == q:
                    matches.append(doc)
            total = len(matches)
            start = (page - 1) * page_size
            end = start + page_size
            return total, matches[start:end]

        if not query:
            # return all docs paginated
            all_ids = list(self.docs.keys())
            total = len(all_ids)
            start = (page - 1) * page_size
            end = start + page_size
            return total, [self.docs[i] for i in all_ids[start:end]]

        q_tokens = tokenize(query)
        if not q_tokens:
            return 0, []

        # retrieve candidates from inverted index
        candidate_ids = None
        for t in q_tokens:
            ids = self.index.get(t, set())
            if candidate_ids is None:
                candidate_ids = set(ids)
            else:
                # union to allow partial matches
                candidate_ids |= ids

        if not candidate_ids:
            # fallback: substring scan across docs (slower)
            candidates = []
            for doc_id, doc in self.docs.items():
                combined = " ".join([str(v).lower() for v in doc.values() if isinstance(v, str)])
                if query.lower() in combined:
                    candidates.append(doc_id)
        else:
            candidates = list(candidate_ids)

        # score and sort
        scored = [(self._score(q_tokens, cid), cid) for cid in candidates]
        scored.sort(key=lambda x: (-x[0], x[1]))
        ordered_ids = [cid for _, cid in scored]
        total = len(ordered_ids)
        start = (page - 1) * page_size
        end = start + page_size
        results = [self.docs[cid] for cid in ordered_ids[start:end]]
        return total, results
