def to_dynamo_score_list(results):
    """Return Dynamo-friendly score rows in a stable field order.

    Row order:
      [score_geom, candidate_view_id, score_tokens, score_fine, confidence_tier, score_total]
    """

    rows = []
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
