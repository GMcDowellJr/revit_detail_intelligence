from dynamo_thin_runner import _normalize_inputs


def test_normalize_inputs_keeps_mode_based_values():
    values = [object(), "index", 5, True]
    assert _normalize_inputs(values) == values


def test_normalize_inputs_converts_legacy_search_shape():
    query = object()
    corpus = [object()]
    assert _normalize_inputs([query, corpus, 7]) == [query, "search", 7]


def test_normalize_inputs_preserves_legacy_sampling_shape():
    query = object()
    corpus = [object()]
    values = [query, corpus, 5, 10, 123]
    assert _normalize_inputs(values) == values
