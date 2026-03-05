from collections import defaultdict

from dse.config import CONFIG, TOKEN_STOPWORDS


def is_valid_token_value(value):
    txt = "" if value is None else str(value).strip()
    if not txt:
        return False
    if txt.lower() in TOKEN_STOPWORDS:
        return False
    return True


def signature_parts_are_valid(signature):
    if "|" not in signature:
        return is_valid_token_value(signature)
    left, right = signature.split("|", 1)
    return is_valid_token_value(left) and is_valid_token_value(right)


def token_weight(kind):
    return CONFIG["token_weights_by_kind"].get(kind, 1.0)


def add_token(tokens, token, kind):
    tokens[token] += token_weight(kind)


def emit_token(tokens, prefix, value, kind):
    value_txt = "" if value is None else str(value).strip()
    if not is_valid_token_value(value_txt):
        return None
    if prefix in ("detail_component", "type_sig") and not signature_parts_are_valid(value_txt):
        return None
    token = "{}:{}".format(prefix, value_txt)
    add_token(tokens, token, kind)
    return token


def safe_name(obj, fallback="<none>"):
    try:
        return obj.Name if obj is not None else fallback
    except Exception:
        return fallback


def resolve_type_name(element, fallback="<unknown-type>"):
    if element is None:
        return fallback

    # FamilyInstance: Symbol.Name is most reliable in CPython3/Python.NET hosts.
    symbol = getattr(element, "Symbol", None)
    if symbol is not None:
        try:
            type_name = safe_name(symbol, fallback=fallback)
            if is_valid_token_value(type_name):
                return type_name
        except Exception:
            pass

    # TextNote / Dimension: access their dedicated type-element properties directly.
    # getattr(obj, "TextNoteType") can resolve to the CLR class object instead of the
    # instance property in Python.NET 3.x when the property name matches the class name;
    # direct attribute access via a lambda avoids that string-based lookup ambiguity.
    for direct_probe in (
        lambda e: e.TextNoteType,
        lambda e: e.DimensionType,
    ):
        try:
            type_obj = direct_probe(element)
            if type_obj is not None:
                type_name = safe_name(type_obj, fallback=fallback)
                if is_valid_token_value(type_name):
                    return type_name
        except Exception:
            pass

    # Generic fallback: GetTypeId() → Document.GetElement() → .Name
    # Do not check IntegerValue == -1: in Revit 2024+ ElementId uses Int64, and large
    # valid IDs overflow Int32 (IntegerValue) to -1, causing false "invalid" detection.
    # Let GetElement() return None for the real InvalidElementId instead.
    doc = getattr(element, "Document", None)
    if doc is None:
        return fallback

    try:
        type_id = element.GetTypeId()
        if type_id is not None:
            type_elem = doc.GetElement(type_id)
            if type_elem is not None:
                type_name = safe_name(type_elem, fallback=fallback)
                if is_valid_token_value(type_name):
                    return type_name
    except Exception:
        pass

    return fallback


def safe_type_name(element, fallback="<unknown-type>"):
    type_name = resolve_type_name(element, fallback=fallback)
    return type_name if is_valid_token_value(type_name) else fallback


def type_signature(element):
    type_name = resolve_type_name(element, fallback="<unknown-type>")
    fam_name = "<no-family>"
    symbol = getattr(element, "Symbol", None)
    if symbol is not None:
        fam_name = safe_name(getattr(symbol, "Family", None), fallback=fam_name)
    return "{}|{}".format(fam_name, type_name)


def family_type_sig(annotation_element):
    return type_signature(annotation_element)


def new_token_store():
    return defaultdict(float)
