import time
import threading
from typing import List, Dict, Any, Optional
import requests
import logging

logger = logging.getLogger("data_loader")


BASE = "https://november7-730026606190.europe-west1.run.app"


def fetch_messages_once(timeout: int = 10, message_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch messages from the external API, paging through skip/limit.

    The upstream API supports `skip` and `limit` query params. This function
    repeatedly requests pages until we've retrieved all known items (using
    the `total` field when present) or until a page returns fewer items than
    requested.

    Returns a flat list of message dicts.
    """
    url = f"{BASE}/messages/"
    all_items: List[Dict[str, Any]] = []
    skip = 0

    # If message_limit is not provided, try to discover the total count from the API
    if message_limit is None:
        try:
            probe = requests.get(url, params={"skip": 0, "limit": 1}, timeout=timeout)
            probe.raise_for_status()
            pdata = probe.json()
            if isinstance(pdata, dict) and pdata.get("total"):
                # use total as the target message limit (attempt to fetch all in one request)
                message_limit = int(pdata.get("total"))
        except requests.exceptions.RequestException:
            # If probe fails, fall back to paged fetching with the default chunk size
            message_limit = None

    # If we discovered a message_limit (total), attempt to fetch that many in one request.
    # Otherwise fall back to fetching in moderate chunks. Use a slightly smaller
    # chunk by default to be gentler with upstream services and avoid page-level 401/403.
    if message_limit is not None:
        chunk = message_limit
    else:
        chunk = 100

    while True:
        # For each page, allow a small number of retries for transient errors.
        max_retries = 3
        backoff = 0.2
        last_exc = None
        resp = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, params={"skip": skip, "limit": chunk}, timeout=timeout)
                # If we got an HTTP error status, raise to the except block so we can inspect it.
                resp.raise_for_status()
                data = resp.json()
                last_exc = None
                break
            except requests.exceptions.HTTPError as http_err:
                status = getattr(http_err.response, "status_code", None)
                # If upstream returns 401/403, treat as terminal for paging (auth or permission issue).
                if status in (401, 403):
                    logger.error("Upstream returned %s at skip=%s limit=%s - stopping further paging", status, skip, chunk)
                    last_exc = http_err
                    resp = http_err.response
                    data = None
                    break
                # For other HTTP errors, we'll retry a few times then stop and return partial results
                last_exc = http_err
            except requests.exceptions.RequestException as exc:
                last_exc = exc

            # retry with exponential backoff
            logger.warning("Transient error fetching messages (attempt %s/%s) at skip=%s: %s", attempt, max_retries, skip, last_exc)
            time.sleep(backoff)
            backoff *= 2

        if last_exc is not None and data is None:
            # If we encountered a terminal auth error, or exhausted retries, log and stop.
            logger.exception("Failed to fetch messages at skip=%s after %s attempts: %s", skip, max_retries, last_exc)
            break

        # Normalize to items list and optional total
        items: List[Dict[str, Any]] = []
        total: Optional[int] = None

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list):
                items = data["items"]
                total = data.get("total")
            else:
                for key in ("messages", "data", "results"):
                    if key in data and isinstance(data[key], list):
                        items = data[key]
                        total = data.get("total")
                        break
                else:
                    # maybe it's an id->obj mapping
                    if all(isinstance(v, dict) for v in data.values()):
                        items = list(data.values())
        else:
            raise ValueError("Unexpected response shape from messages endpoint")

        if not items:
            break

        all_items.extend(items)

        # If upstream tells us the total, stop when we've got all of them
        if total is not None and len(all_items) >= int(total):
            break

        # If this page returned fewer than requested, we're at the end
        if len(items) < chunk:
            break
        skip += chunk
        # be polite to the upstream service
        time.sleep(0.05)

    return all_items


class DataLoader:
    """Loads messages and optionally refreshes in background."""

    def __init__(self, refresh_interval: Optional[int] = None):
        self.docs = []
        self.refresh_interval = refresh_interval
        self._stop = threading.Event()
        self._thread = None

    def load(self) -> List[Dict[str, Any]]:
        self.docs = fetch_messages_once()
        return self.docs

    def start_periodic(self):
        if not self.refresh_interval:
            return
        if self._thread and self._thread.is_alive():
            return

        def run():
            while not self._stop.wait(self.refresh_interval):
                try:
                    self.load()
                except Exception:
                    # ignore refresh failures; next cycle will try again
                    pass

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            # clear reference to thread to avoid some interpreter shutdown races
            self._thread = None
