from dse.output_format import to_dynamo_score_list


def test_to_dynamo_score_list_field_order():
    results = [
        {
            "candidate_view_id": 42,
            "score_total": 0.91,
            "score_tokens": 0.88,
            "score_geom": 0.93,
            "score_fine": 0.70,
            "confidence_tier": "HIGH",
        }
    ]

    rows = to_dynamo_score_list(results)
    assert rows == [
        [
            "score_geom",
            "candidate_view_id",
            "score_tokens",
            "score_fine",
            "confidence_tier",
            "score_total",
        ],
        [0.93, 42, 0.88, 0.70, "HIGH", 0.91],
    ]


def test_to_dynamo_score_list_can_omit_header():
    rows = to_dynamo_score_list(
        [{"candidate_view_id": 1, "score_geom": 0.1}], include_header=False
    )
    assert rows == [[0.1, 1, 0.0, 0.0, "LOW", 0.0]]
