# System Architecture

```mermaid
flowchart TD

%% INPUT
A[User selects exterior wall face]

%% MODEL ANALYSIS LAYER
subgraph Model Analysis
B[Scan facade band]
C[Generate candidate section locations]
D[Create section views]
E[Extract geometry from elements intersecting section plane]
F[Cluster endpoints into detail regions]
end

%% FEATURE EXTRACTION LAYER
subgraph Feature Extraction
G[Extract semantic tokens<br/>category type context]
H[Build geometry fingerprint<br/>normalized edge patterns]
I[Assemble feature vector]
end

%% DETAIL INDEX
subgraph Detail Index
J[Index project details]
K[Index library drafting views]
end

%% SIMILARITY ENGINE
subgraph Similarity Engine
L[Compute similarity scores]
M[Rank candidate matches]
end

%% OUTPUT
subgraph Output
N[High confidence reuse]
O[Similar detail candidates]
P[New detail likely required]
end

A --> B
B --> C
C --> D
D --> E
E --> F

F --> G
F --> H

G --> I
H --> I

I --> L
J --> L
K --> L

L --> M

M --> N
M --> O
M --> P
