# Geometry Fingerprint

## Purpose

The geometry fingerprint provides a simplified representation of a cluster of endpoints that captures its structural pattern.

The goal is to recognize similar conditions even when dimensions vary.

---

## Endpoint Extraction

Curves intersecting the section plane are converted into endpoints.

These endpoints represent the structural outline of the condition.

---

## Canonical Coordinate Frame

Endpoints are expressed in the local coordinate system of the view.

This ensures that comparisons are not affected by global model orientation.

---

## Scale Normalization

Distances are normalized using a characteristic scale derived from the cluster.

Typical choices include:

- median nearest-neighbor distance
- cluster bounding box dimension

---

## Neighborhood Graph

Each point is connected to its nearest neighbors.

This graph captures local structural relationships between features.

---

## Histogram Construction

Edge relationships are summarized into histograms such as:

- edge length distribution
- edge orientation distribution

These histograms form the geometry fingerprint.

---

## Properties

The fingerprint is designed to be:

- translation invariant
- scale tolerant
- robust to small perturbations

Exact geometric equality is not required for a match.
