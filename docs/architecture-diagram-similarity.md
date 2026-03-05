%% Detail Search Engine - end-to-end architecture (drafting views)
%% Notes:
%% - "Symbol Cache" exists to bypass GetGeometry blind spots for Detail Item families.
%% - Rendered PNG is optional but becomes the tie-breaker when geometry coverage is low.
%% - Pipeline supports incremental cache fill: only build symbol signatures when missing.

flowchart TD

  A[Corpus: Drafting Views] --> B[Scan Views: collect elements]
  B --> C[Tokenize View: IDF-ready tokens]
  B --> D[Collect Symbol Types Used: Family|Type keys]
  B --> E[Extract View-owned Geometry: detail lines, filled region boundaries]
  B --> F[Layout Features: bbox centers, bbox size/aspect]

  D --> G{Symbol Cache hit?}
  G -->|Yes| H[Load Symbol Descriptor]
  G -->|No| I[Build Symbol Descriptor]

  I --> J[Temp Drafting View Builder]
  J --> K[Place 1 instance per Symbol Type]
  K --> L[Isolate Instance]
  L --> M[Render PNG: graphics-only channel]
  M --> N[Normalize: crop, center, fixed size]
  N --> O[Descriptor: affine normalize + rotation invariance]
  O --> P[Store in Symbol Cache]
  P --> H

  C --> Q[Candidate Retrieval]
  H --> Q
  E --> Q
  F --> Q

  Q --> R[Top-N Candidates]
  R --> S{Need Visual Re-rank?}
  S -->|No| T[Return Ranked Results + Explanations]
  S -->|Yes| U[Render View PNGs: standardized crop/visibility]
  U --> V[Raster Similarity: edge-map/descriptor]
  V --> W[Re-rank Top-N]
  W --> T

  T --> X[Explainability Pack]
  X --> X1[Shared rare tokens + counts]
  X --> X2[Symbol overlap + key symbol matches]
  X --> X3[Geometry coverage + layout deltas]
