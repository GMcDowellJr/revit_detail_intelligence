# Architecture Diagram

```mermaid
flowchart TD

A[User selects exterior wall face]

A --> B[Scan facade band]
B --> C[Generate candidate section locations]

C --> D[Create section view]
D --> E[Extract curves from model elements intersecting the section plane]

E --> F[Collect curve endpoints]
F --> G[Cluster endpoints into candidate detail regions]

G --> H[Extract semantic tokens: category, type, context]
G --> I[Build geometry fingerprint: normalized length and angle histograms]

H --> J[Assemble feature vector]
I --> J

J --> K[Compare against indexed project details]
J --> L[Compare against indexed library drafting views]

K --> M[Compute similarity scores]
L --> M

M --> N[Rank matches]

N --> O[High confidence: reuse existing detail]
N --> P[Medium confidence: similar detail candidate]
N --> Q[Low confidence: new detail likely required]
