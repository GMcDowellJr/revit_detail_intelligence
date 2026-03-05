SCORE_LIST_SCHEMA = [
    "score_geom",
    "candidate_view_id",
    "score_tokens",
    "score_fine",
    "confidence_tier",
    "score_total",
]


def to_dynamo_score_list(results, include_header=True):
    """Return Dynamo-friendly score rows in a stable field order.

    Row order:
      [score_geom, candidate_view_id, score_tokens, score_fine, confidence_tier, score_total]

    When ``include_header`` is True, the first row is the string schema.
    """

    rows = [list(SCORE_LIST_SCHEMA)] if include_header else []
    for row in results:
        rows.append(
            [
                row.get("score_geom", 0.0),
                row.get("candidate_view_id"),
                row.get("score_tokens", 0.0),
                row.get("score_fine", 0.0),
                row.get("confidence_tier", "LOW"),
                row.get("score_total", 0.0),
            ]
        )
    return rows
