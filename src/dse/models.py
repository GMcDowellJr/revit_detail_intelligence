from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class ViewFeatures:
    view_id: int
    view_kind: str
    tokens: Dict[str, float]
    geom_fingerprint: List[float]
    fine_metrics: Dict[str, float]
    debug: Dict[str, Any] = field(default_factory=dict)
