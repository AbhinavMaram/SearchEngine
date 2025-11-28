from search_engine import SearchEngine


def test_basic_index_and_search():
    docs = [
        {"id": "1", "text": "Hello world"},
        {"id": "2", "text": "Goodbye world"},
        {"id": "3", "text": "Hello there"},
    ]
    se = SearchEngine()
    se.build_index(docs, id_field="id")
    total, results = se.search("hello", page=1, page_size=10)
    assert total >= 2
    ids = {r["id"] for r in results}
    assert "1" in ids or "3" in ids
