# Revit Detail Intelligence

## Overview

Revit Detail Intelligence explores a deterministic method for identifying construction conditions within a model and suggesting relevant construction details based on structural similarity.

Rather than relying on visual inspection of drawings, the system analyzes the geometry produced where model elements intersect a section plane. From this geometry it derives simplified structural signatures that can be compared across details and drafting views. The goal is to identify when two conditions are essentially the same—even if their dimensions vary slightly—and surface opportunities to reuse existing project or library details.

The system is intended as **decision support**, not automation. It highlights candidate sections, identifies areas likely requiring detailing, and suggests similar details with explainable confidence.

---

## Problem

Large projects often contain many construction conditions that are repeated with minor variation. Designers typically locate details manually by browsing libraries or searching through project sheets. This process is:

- time-consuming
- inconsistent across teams
- prone to duplication of similar details

There is currently no systematic way for the model to recognize that a construction condition is similar to one that has already been detailed.

---

## Approach

The system analyzes section geometry and model context to build a feature-based description of a construction condition. These features are then compared against indexed details to find similar patterns.

Key principles:

- deterministic algorithms
- explainable similarity metrics
- tolerance for dimensional variation
- independence from fragile view graphics

---

## Pipeline Summary

1. **Section Candidate Generation**

   A user selects an exterior wall face.  
   The system scans a narrow vertical band and identifies locations where construction conditions change.

2. **Section Geometry Extraction**

   Geometry from model elements intersecting the section plane is collected.

3. **Endpoint Clustering**

   Line endpoints are grouped to identify regions of geometric complexity that likely require detailing.

4. **Feature Extraction**

   Each cluster is described using:

   - semantic tokens (element categories and types)
   - normalized geometric fingerprints
   - optional fine-grained metrics

5. **Detail Indexing**

   Existing details and drafting views are processed to produce the same feature representation.

6. **Similarity Matching**

   The system compares features and ranks other details according to structural similarity.

7. **Confidence Scoring**

   Matches are categorized into:

   - high confidence (likely the same condition)
   - medium confidence (similar)
   - low confidence (likely different)

---

## Repository Structure

docs/
- system-overview.md
- pipeline-architecture.md
- geometry-fingerprint.md
- similarity-matching.md
- detail-indexing.md
- calibration-and-validation.md

research/
- experiments and exploratory notes

src/
- implementation code

examples/
- sample inputs and outputs

---

## Status

Early research and prototype phase.

Current focus:

- defining feature representations
- validating similarity metrics
- building deterministic geometry fingerprints

---

## Non-Goals

This project does not attempt to:

- perform image recognition on drawings
- automatically place details
- replace design judgement

---

## Related Work

This project complements other model analysis pipelines such as:

- Revit Fingerprint (standards analysis)
- View-on-Paper / Scope Stability Metrics

---

## License

TBD
