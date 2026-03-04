# Detail Indexing

## Purpose

All candidate details must be converted into a comparable feature representation before matching.

This process is called indexing.

---

## Model-Based Details

Detail views associated with model geometry are indexed using:

- contributing element categories
- family/type signatures
- geometry fingerprints

---

## Drafting Views

Drafting views lack direct model references.

Instead they are indexed using:

- detail components
- line styles
- filled regions
- dimension types
- geometry fingerprints derived from drafting lines

---

## Feature Storage

Each indexed detail produces a feature vector containing:

- token multiset
- geometry fingerprint
- optional metadata

These vectors are stored in a searchable index.

---

## Update Strategy

The index can be regenerated when:

- new details are added
- detail content changes
- library content is updated
