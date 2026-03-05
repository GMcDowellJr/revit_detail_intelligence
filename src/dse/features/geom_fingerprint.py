import math

from dse.config import EPS
from dse.revit_api.geometry_2d import bbox_diagonal


def k_nearest_neighbors(points2d, i, k):
    x0, y0 = points2d[i]
    rows = []
    for j, (x, y) in enumerate(points2d):
        if i == j:
            continue
        d = math.hypot(x - x0, y - y0)
        rows.append((d, round(x, 9), round(y, 9), j))
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    return [r[3] for r in rows[:k]]


def robust_scale(points2d, k):
    if len(points2d) < (k + 1):
        return max(EPS, bbox_diagonal(points2d))
    dists = []
    for i in range(len(points2d)):
        for j in k_nearest_neighbors(points2d, i, k):
            dists.append(math.hypot(points2d[j][0] - points2d[i][0], points2d[j][1] - points2d[i][1]))
    if not dists:
        return max(EPS, bbox_diagonal(points2d))
    dists.sort()
    med = dists[len(dists) // 2]
    if med <= EPS:
        return max(EPS, bbox_diagonal(points2d))
    return med


def bin_index(v, bins):
    for i in range(len(bins) - 1):
        if bins[i] <= v < bins[i + 1]:
            return i
    return len(bins) - 2


def normalize_l1(vec):
    s = sum(vec)
    if s <= EPS:
        return [0.0 for _ in vec]
    return [v / s for v in vec]


def geom_fingerprint_knn(points2d, k, len_bins, ang_bins):
    n = len(points2d)
    if n < 2:
        return [0.0] * ((len(len_bins) - 1) * (len(ang_bins) - 1))
    edges = []
    for i in range(n):
        for j in k_nearest_neighbors(points2d, i, k):
            if i < j:
                dx = points2d[j][0] - points2d[i][0]
                dy = points2d[j][1] - points2d[i][1]
                length = math.hypot(dx, dy)
                angle = abs(math.degrees(math.atan2(dy, dx)))
                if angle > 180.0:
                    angle = 360.0 - angle
                edges.append((length, angle))

    cols = len(ang_bins) - 1
    hist = [0.0] * ((len(len_bins) - 1) * cols)
    for length, angle in edges:
        bi = bin_index(length, len_bins)
        bj = bin_index(angle, ang_bins)
        hist[bi * cols + bj] += 1.0
    return normalize_l1(hist)
