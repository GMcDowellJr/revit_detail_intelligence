from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class SymbolCacheEntry:
    symbol_id: int
    family_name: str
    type_name: str
    metadata: Dict[str, str]


class SymbolCache(object):
    """Stub for future symbol/raster cache integration."""

    def __init__(self):
        self._entries = {}

    def get(self, symbol_id) -> Optional[SymbolCacheEntry]:
        return self._entries.get(symbol_id)

    def put(self, entry: SymbolCacheEntry):
        self._entries[entry.symbol_id] = entry

    def clear(self):
        self._entries = {}
