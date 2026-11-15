"""A tiny in-memory stand-in for the PyMongo calls this app uses.

DEVELOPMENT ONLY. Data disappears when the process stops and is not shared between
gunicorn workers. It is used solely when MONGODB_URI is unset and ALLOW_MEMORY_DB is on,
and /api/health reports `db_mode: "memory"` so it is never mistaken for real storage.
"""
import copy
import threading


class MemoryDuplicateKey(Exception):
    pass


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: (d.get(key) is None, d.get(key)), reverse=direction == -1)
        return self

    def limit(self, n):
        if n:
            self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


def _matches(doc, flt):
    return all(doc.get(k) == v for k, v in (flt or {}).items())


def _project(doc, projection):
    out = copy.deepcopy(doc)
    if projection and projection.get("_id") == 0:
        out.pop("_id", None)
    return out


class MemoryCollection:
    def __init__(self):
        self._docs: list[dict] = []
        self._unique: list[str] = []
        self._lock = threading.Lock()

    def create_index(self, key, unique=False, **_):
        if unique and key not in self._unique:
            self._unique.append(key)

    def insert_one(self, doc):
        with self._lock:
            for key in self._unique:
                if any(d.get(key) == doc.get(key) for d in self._docs):
                    raise MemoryDuplicateKey(key)
            self._docs.append(copy.deepcopy(doc))

    def find_one(self, flt=None, projection=None):
        with self._lock:
            for d in self._docs:
                if _matches(d, flt):
                    return _project(d, projection)
        return None

    def find(self, flt=None, projection=None):
        with self._lock:
            return _Cursor([_project(d, projection) for d in self._docs if _matches(d, flt)])

    def update_one(self, flt, update):
        with self._lock:
            for d in self._docs:
                if _matches(d, flt):
                    d.update(copy.deepcopy(update.get("$set", {})))
                    return 1
        return 0

    def delete_one(self, flt):
        with self._lock:
            for i, d in enumerate(self._docs):
                if _matches(d, flt):
                    del self._docs[i]
                    return 1
        return 0

    def delete_many(self, flt):
        with self._lock:
            before = len(self._docs)
            self._docs = [d for d in self._docs if not _matches(d, flt)]
            return before - len(self._docs)


class MemoryDB:
    def __init__(self):
        self._cols: dict[str, MemoryCollection] = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, MemoryCollection())
