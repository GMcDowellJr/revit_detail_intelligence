# How the System Recognizes Similar Details

```mermaid
flowchart TD

subgraph Left[Candidate condition from model section]
A1[Section plane geometry from intersecting model elements]
A2[Endpoints and curves]
A3[Clustered region candidate detail area]
A4[Semantic tokens: category, type, context]
A5[Geometry fingerprint: normalized edge-length and angle histograms]
A6[Feature vector]
end

subgraph Right[Existing details in project or library]
B1[Detail or Drafting View]
B2[Extract tokens from elements or drafting content]
B3[Extract geometry curves and endpoints]
B4[Geometry fingerprint: normalized edge-length and angle histograms]
B5[Feature vector]
end

A1 --> A2 --> A3
A3 --> A4 --> A6
A3 --> A5 --> A6

B1 --> B2 --> B5
B1 --> B3 --> B4 --> B5

A6 --> C[Similarity engine weighted scoring]
B5 --> C

C --> D1[Match 1 High confidence]
C --> D2[Match 2 Medium confidence]
C --> D3[Match 3 Low confidence]
```

## Notes

- The geometry fingerprint is designed to tolerate dimensional variation such as different wall thicknesses or small offsets by normalizing lengths and binning geometric relationships.
- Semantic tokens provide contextual signals derived from the elements or drafting content present in the detail, helping reduce false matches.
- The system produces ranked suggestions with confidence tiers rather than making automated drafting decisions.
