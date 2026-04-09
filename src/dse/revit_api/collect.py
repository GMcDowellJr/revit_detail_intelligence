import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (  # noqa: E402
    BuiltInParameter,
    CategoryType,
    CurveElement,
    DetailCurve,
    DetailLine,
    Dimension,
    ElementId,
    FamilyInstance,
    FilledRegion,
    FilteredElementCollector,
    TextNote,
    View,
    ViewType,
)

try:
    clr.AddReference("RevitServices")
    from RevitServices.Persistence import DocumentManager  # noqa: E402
except Exception:
    DocumentManager = None


def current_doc():
    if DocumentManager is None:
        return None
    try:
        return DocumentManager.Instance.CurrentDBDocument
    except Exception:
        return None


def first_item(value):
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return value[0]
    return value


def unwrap_dynamo_element(value):
    if value is None:
        return None
    try:
        return value.InternalElement
    except Exception:
        return value


def coerce_view(value, fallback_doc=None):
    candidate = unwrap_dynamo_element(first_item(value))
    if isinstance(candidate, View):
        return candidate

    doc = fallback_doc or current_doc()
    if doc is None:
        return None

    if isinstance(candidate, ElementId):
        elem = doc.GetElement(candidate)
        return elem if isinstance(elem, View) else None

    try:
        elem = doc.GetElement(ElementId(int(candidate)))
        return elem if isinstance(elem, View) else None
    except Exception:
        return None


def coerce_views(values, fallback_doc=None):
    if values is None:
        return []
    seq = values if isinstance(values, list) else [values]
    out = []
    for value in seq:
        view = coerce_view(value, fallback_doc=fallback_doc)
        if view is not None:
            out.append(view)
    return out


def safe_name(obj, fallback="<none>"):
    try:
        return obj.Name if obj is not None else fallback
    except Exception:
        return fallback


def class_name(element):
    try:
        return element.GetType().Name
    except Exception:
        return "<unknown-class>"


def category_name(element):
    return safe_name(getattr(element, "Category", None), fallback="<none>")


def increment(counter, key, amount=1):
    counter[key] = counter.get(key, 0) + amount


def category_type_label(category):
    if category is None:
        return None
    cat_type = getattr(category, "CategoryType", None)
    if cat_type is None:
        return None
    enum_by_int = {
        int(CategoryType.Model): "Model",
        int(CategoryType.Annotation): "Annotation",
    }
    try:
        return enum_by_int.get(int(cat_type), str(cat_type))
    except Exception:
        try:
            return cat_type.ToString()
        except Exception:
            return str(cat_type)


def get_view_elements(view):
    doc = view.Document
    return list(FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType().ToElements())


def get_model_elements_contributing_to_view(view, elements=None):
    elems = []
    source = elements if elements is not None else get_view_elements(view)
    for elem in source:
        cat = elem.Category
        if cat is None:
            continue
        if category_type_label(cat) == "Model":
            elems.append(elem)
    return elems


def is_annotation_like(element):
    cat = getattr(element, "Category", None)
    if category_type_label(cat) == "Annotation":
        return True
    if isinstance(element, (FamilyInstance, FilledRegion, Dimension, TextNote, CurveElement)):
        return True
    return False


def classify_view_kind(view, elements=None):
    if view.ViewType == ViewType.DraftingView:
        return "DRAFTING"
    if view.ViewType in (ViewType.Detail, ViewType.Section, ViewType.Elevation):
        has_model = any(
            category_type_label(e.Category) != "Annotation"
            for e in (elements if elements is not None else get_view_elements(view))
        )
        return "DETAIL_MODEL" if has_model else "DETAIL_DRAFTING"
    return "DETAIL_DRAFTING"


def token_assignment_policy(config, stopwords):
    return {
        "DETAIL_MODEL": {
            "category": "token = 'category:' + element category name",
            "type_sig": "token = 'type_sig:' + family|type signature",
        },
        "DETAIL_DRAFTING_OR_DRAFTING": {
            "FamilyInstance": "token = 'detail_component:' + family|type signature",
            "FilledRegion": "token = 'fill_region:' + filled region name",
            "Dimension": "token = 'dim_style:' + dimension style name",
            "TextNote": "token = 'text_type:' + text type name",
            "CurveElement": "token = 'line_style:' + line style name",
            "Unmapped annotation": "no token (reported in collected_info.reason)",
        },
        "weights_by_kind": dict(config["token_weights_by_kind"]),
        "stopword_values": sorted(stopwords),
    }



def is_family_instance(element):
    return isinstance(element, FamilyInstance)


def is_filled_region(element):
    return isinstance(element, FilledRegion)


def is_dimension(element):
    return isinstance(element, Dimension)


def is_text_note(element):
    return isinstance(element, TextNote)


def is_curve_annotation(element):
    return isinstance(element, (DetailCurve, DetailLine, CurveElement))


def is_view(element):
    return isinstance(element, View)


def element_type_name_from_params(element):
    """Return the Revit type name by reading built-in string parameters.

    Attempt 1: instance-element parameters (SYMBOL_NAME_PARAM works for
    FamilyInstance / AnnotationSymbol; both BIPs return null for system families).
    Attempt 2: type-element parameters via GetTypeId() → GetElement() — bypasses
    the Python.NET 3.x virtual-dispatch bug where type_elem.Name raises.
    """
    for bip in (BuiltInParameter.SYMBOL_NAME_PARAM, BuiltInParameter.ALL_MODEL_TYPE_NAME):
        try:
            param = element.get_Parameter(bip)
            if param is not None:
                val = param.AsString()
                if val:
                    return val
        except Exception:
            continue

    try:
        type_id = element.GetTypeId()
        if type_id is not None:
            type_elem = element.Document.GetElement(type_id)
            if type_elem is not None:
                type_bips = (
                    BuiltInParameter.SYMBOL_NAME_PARAM,
                    BuiltInParameter.ALL_MODEL_TYPE_NAME,
                )
                for bip in type_bips:
                    try:
                        param = type_elem.get_Parameter(bip)
                        if param is not None:
                            val = param.AsString()
                            if val:
                                return val
                    except Exception:
                        continue
    except Exception:
        pass

    return None
