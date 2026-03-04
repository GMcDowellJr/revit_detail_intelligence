# ============================================================
# DETAIL / DRAFTING VIEW SIMILARITY (FEATURE-BASED MATCHING)
# Scope: "this view looks like these other views"
# Deterministic, explainable, scale-tolerant
# ============================================================

# -------------------------
# CONFIG / POLICY (tunable)
# -------------------------
CONFIG:
  kNN_k = 3
  len_bins = [0.00, 0.10, 0.20, 0.35, 0.50, 0.70, 1.00, 1.40, 2.00, +INF]  # normalized
  ang_bins_deg = [0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180]   # 0..180 symmetric
  tol_coord = 1/256 ft   # or mm equivalent; used only for deterministic tie-breaking
  weights:
    w_tokens = 0.55
    w_geom   = 0.35
    w_fine   = 0.10

  confidence_thresholds:
    HIGH_min = 0.85
    MED_min  = 0.65

  # token weighting (optional)
  token_weights_by_kind = {
    "category": 1.0,
    "type_sig": 1.5,
    "line_style": 1.0,
    "detail_component": 2.0,
    "fill_region": 1.2,
    "dim_style": 1.2,
    "text_type": 0.8
  }

# -------------------------
# DATA TYPES
# -------------------------
TYPE ViewFeatures:
  view_id
  view_kind              # "DETAIL_MODEL", "DETAIL_DRAFTING", "DRAFTING"
  tokens: multiset(token_string -> count or weight)
  geom_fingerprint: vector<float>     # normalized histogram(s)
  fine_metrics: dict<string,float>    # optional tie-breakers
  debug: dict                          # optional: explainability data

TYPE MatchResult:
  candidate_view_id
  score_total
  score_tokens
  score_geom
  score_fine
  confidence_tier        # "HIGH"|"MEDIUM"|"LOW"
  explanation_top_terms  # list of (term, contribution)
  explanation_diffs      # optional: top diffs vs candidate

# -------------------------
# MAIN ENTRYPOINT
# -------------------------
function FIND_SIMILAR_VIEWS(query_view, corpus_views, topN):
  Q = EXTRACT_FEATURES(query_view)

  # Pre-extracted features for corpus should be cached/indexed.
  # If not cached:
  CorpusFeat = [EXTRACT_FEATURES(v) for v in corpus_views]

  results = []
  for C in CorpusFeat:
    s_tokens = TOKEN_SIMILARITY(Q.tokens, C.tokens)
    s_geom   = GEOM_SIMILARITY(Q.geom_fingerprint, C.geom_fingerprint)
    s_fine   = FINE_SIMILARITY(Q.fine_metrics, C.fine_metrics)

    s_total = CONFIG.weights.w_tokens*s_tokens +
              CONFIG.weights.w_geom*s_geom +
              CONFIG.weights.w_fine*s_fine

    tier = CONFIDENCE_TIER(s_total)

    results.append( BUILD_MATCH_RESULT(C.view_id, s_total, s_tokens, s_geom, s_fine, tier,
                                       EXPLAIN_MATCH(Q, C)) )

  # deterministic sort: score desc, then stable id
  results.sort(key = (-score_total, candidate_view_id))
  return results[0:topN]

# -------------------------
# FEATURE EXTRACTION
# -------------------------
function EXTRACT_FEATURES(view):
  kind = CLASSIFY_VIEW_KIND(view)  # "DETAIL_MODEL" vs "DRAFTING" etc.

  # 1) TOKEN FEATURES
  tokens = EMPTY_MULTISET()

  if kind == "DETAIL_MODEL":
    # Model-derived: tokens from elements that generate cut/visible geometry
    # (implementation dependent: intersecting elements in section plane, or visible solids/edges)
    elems = GET_MODEL_ELEMENTS_CONTRIBUTING_TO_VIEW(view)

    for e in elems:
      tokens.add("category:" + e.category_name, weight=WEIGHT("category"))
      tokens.add("type_sig:" + TYPE_SIGNATURE(e), weight=WEIGHT("type_sig"))

      # Optional: coarse flags (avoid fragile parameters)
      if e.is_hosted_opening: tokens.add("flag:opening_present", weight=1.0)
      if e.is_slab_edge:      tokens.add("flag:slab_edge", weight=1.0)

  else:
    # Drafting: tokens from view contents (2D elements)
    ann = GET_ANNOTATION_ELEMENTS(view)

    for a in ann:
      if a.kind == "DetailComponent":
        tokens.add("detail_component:" + FAMILY_TYPE_SIG(a), weight=WEIGHT("detail_component"))
      if a.kind == "FilledRegion":
        tokens.add("fill_region:" + a.type_name, weight=WEIGHT("fill_region"))
      if a.kind == "Dimension":
        tokens.add("dim_style:" + a.dimension_type_name, weight=WEIGHT("dim_style"))
      if a.kind == "Text":
        tokens.add("text_type:" + a.text_type_name, weight=WEIGHT("text_type"))
      if a.kind == "Line":
        tokens.add("line_style:" + a.line_style_name, weight=WEIGHT("line_style"))

  # 2) GEOMETRY FINGERPRINT
  # Extract 2D curve endpoints within the view plane / view coordinate system.
  # For model views: only curves from elements intersecting the section plane (your constraint).
  # For drafting: curves are drafting lines/arcs.
  curves = GET_2D_CURVES_IN_VIEW(view, only_model_intersections = (kind=="DETAIL_MODEL"))
  pts = ENDPOINTS_FROM_CURVES(curves)

  # (optional) filter points: remove tiny/duplicate points by tolerance grid
  pts = DEDUPE_POINTS_BY_GRID(pts, tol=CONFIG.tol_coord)

  # canonical frame: view plane axes (Right/Up)
  # represent all points in that local 2D coordinate system
  pts2 = TO_VIEW_LOCAL_2D(pts, view.right_dir, view.up_dir, view.origin)

  # scale normalization: robust characteristic length
  # (prefer median kNN edge length; fallback to bbox diagonal)
  scale = ROBUST_SCALE(pts2, k=CONFIG.kNN_k)
  ptsN = [p / scale for p in pts2]    # elementwise division

  geom_fp = GEOM_FINGERPRINT_KNN(ptsN, k=CONFIG.kNN_k,
                                 len_bins=CONFIG.len_bins,
                                 ang_bins=CONFIG.ang_bins_deg)

  # 3) FINE METRICS (optional tie-breakers)
  fine = {}
  fine["pt_count"] = len(ptsN)
  fine["bbox_aspect"] = BBOX_ASPECT_RATIO(ptsN)
  fine["linework_density"] = LINEWORK_DENSITY(curves, bbox=BBOX(ptsN))

  return ViewFeatures(view.id, kind, tokens, geom_fp, fine,
                      debug={"scale":scale, "pt_count":len(ptsN)})

# -------------------------
# GEOMETRY FINGERPRINT
# -------------------------
function GEOM_FINGERPRINT_KNN(points2D, k, len_bins, ang_bins):
  # Build sparse deterministic edges via k-nearest-neighbors
  # Determinism: tie-break by (distance, x, y) with tolerance rounding
  edges = []
  for i in range(0, N):
    nbrs = K_NEAREST_NEIGHBORS(points2D, i, k, deterministic=true)
    for j in nbrs:
      if j == i: continue
      if i < j:
        v = points2D[j] - points2D[i]
        length = NORM(v)
        angle  = ABS_ANGLE_DEG(v)          # 0..180 (treat directionless)
        edges.append((length, angle))

  # Histogram in 2D bins (length x angle)
  H = zeros(len(len_bins)-1, len(ang_bins)-1)

  for (L, A) in edges:
    bi = BIN_INDEX(L, len_bins)
    bj = BIN_INDEX(A, ang_bins)
    H[bi][bj] += 1

  # Normalize to unit sum (or unit L2 norm)
  return NORMALIZE_VECTOR(FLATTEN(H), norm="L1")

# -------------------------
# SIMILARITY FUNCTIONS
# -------------------------
function TOKEN_SIMILARITY(tokensA, tokensB):
  # Weighted Jaccard on multisets (counts/weights)
  # sim = sum(min(a_i, b_i)) / sum(max(a_i, b_i))
  keys = UNION_KEYS(tokensA, tokensB)
  num = 0
  den = 0
  for k in keys:
    a = tokensA.get(k, 0)
    b = tokensB.get(k, 0)
    num += MIN(a, b)
    den += MAX(a, b)
  if den == 0: return 0
  return num / den

function GEOM_SIMILARITY(fpA, fpB):
  # cosine similarity on normalized hist vectors
  return COSINE_SIM(fpA, fpB)

function FINE_SIMILARITY(fineA, fineB):
  # optional; keep weak to avoid brittleness
  # Example: penalize extreme mismatch in point count / bbox aspect
  if fineA.empty or fineB.empty: return 0.5  # neutral
  s1 = GAUSSIAN_SIM(fineA["bbox_aspect"], fineB["bbox_aspect"], sigma=0.5)
  s2 = GAUSSIAN_SIM(fineA["linework_density"], fineB["linework_density"], sigma=0.5)
  return 0.5*s1 + 0.5*s2

# -------------------------
# CONFIDENCE + EXPLANATION
# -------------------------
function CONFIDENCE_TIER(score):
  if score >= CONFIG.confidence_thresholds.HIGH_min: return "HIGH"
  if score >= CONFIG.confidence_thresholds.MED_min:  return "MEDIUM"
  return "LOW"

function EXPLAIN_MATCH(Q, C):
  # Provide top contributing tokens and dominant geom bins for transparency
  common = INTERSECT_KEYS(Q.tokens, C.tokens)
  token_contrib = []
  for k in common:
    token_contrib.append((k, MIN(Q.tokens[k], C.tokens[k])))
  token_contrib.sort(key=(-contrib, k))
  top_terms = token_contrib[0:10]

  # Optionally highlight top geom bins where both histograms are high
  geom_contrib = TOP_SHARED_BINS(Q.geom_fingerprint, C.geom_fingerprint, top=10)

  return {
    "top_shared_tokens": top_terms,
    "top_shared_geom_bins": geom_contrib
  }

# -------------------------
# HELPERS (sketches)
# -------------------------
function ROBUST_SCALE(points2D, k):
  if len(points2D) < (k+1):
    return MAX( EPS, BBOX_DIAGONAL(points2D) )

  # median of kNN distances across all points
  dists = []
  for i in range(0, N):
    nbrs = K_NEAREST_NEIGHBORS(points2D, i, k, deterministic=true)
    for j in nbrs:
      dists.append( NORM(points2D[j]-points2D[i]) )
  med = MEDIAN(dists)
  if med <= EPS: return MAX(EPS, BBOX_DIAGONAL(points2D))
  return med

function TYPE_SIGNATURE(element):
  # stable-ish signature; choose policy based on your standards
  # e.g., "FamilyName|TypeName" or hashed subset of key parameters
  return element.family_name + "|" + element.type_name

function FAMILY_TYPE_SIG(annotation_element):
  return annotation_element.family_name + "|" + annotation_element.type_name

function WEIGHT(kind):
  return CONFIG.token_weights_by_kind.get(kind, 1.0)
