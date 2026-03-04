# Calibration and Validation

## Purpose

Similarity scores must be calibrated to ensure that confidence levels are meaningful.

---

## Ground Truth Dataset

A set of known detail relationships should be assembled.

Examples include:

- duplicate details within a project
- known variations of a standard detail
- unrelated details

This dataset forms the baseline for evaluation.

---

## Metrics

Evaluation may include:

- true positive rate
- false positive rate
- ranking accuracy

---

## Threshold Calibration

Similarity thresholds should be tuned so that:

- high-confidence matches are rarely incorrect
- medium-confidence matches remain useful review candidates

---

## Iteration

Feature definitions and weights should be refined based on validation results.

The goal is stable performance across multiple projects.
