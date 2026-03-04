# Similarity Matching

## Overview

Similarity between details is evaluated by comparing feature sets derived from geometry and model context.

Each detail is represented as:

- semantic tokens
- geometry fingerprint
- optional fine metrics

---

## Token Similarity

Tokens represent elements or annotations present in a detail.

Examples:

- element categories
- family types
- drafting components
- line styles

Similarity is computed using weighted overlap metrics.

---

## Geometry Similarity

Geometry fingerprints are compared using statistical distance metrics.

Typical measures include:

- cosine similarity
- histogram distance

These measures evaluate how closely the structural patterns align.

---

## Combined Score

The final similarity score is a weighted combination of token and geometry similarity.

similarity = w_tokens * token_similarity
* w_geometry * geometry_similarity
* w_fine * fine_similarity

---

## Confidence Categories

Scores are categorized into:

High confidence

Likely represents the same construction condition.

Medium confidence

Similar but not identical.

Low confidence

Probably different conditions.

---

## Explainability

For each match, the system can report:

- shared tokens
- dominant geometry patterns
- differences from the candidate detail
