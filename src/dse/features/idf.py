import json
import math
from collections import defaultdict


def build_token_df_from_features(corpus_features):
    token_df = defaultdict(int)
    for feat in corpus_features:
        for token in feat.tokens.keys():
            token_df[token] += 1
    return dict(token_df), len(corpus_features)


def build_token_idf(token_df, doc_count):
    n = max(1, int(doc_count))
    idf = {}
    for token, df in token_df.items():
        if df <= 0:
            continue
        idf[token] = math.log(float(n) / float(df))
    return idf


def serialize_idf_map(token_idf):
    return json.dumps(token_idf, sort_keys=True)
