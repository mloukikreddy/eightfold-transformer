"""Apply runtime output config: select/rename/normalize fields, missing-value policy."""
import re

_PATH_RE = re.compile(r"([^\[\].]+)|\[(\d+)\]")


def _get_path(record, path):
    tokens = _PATH_RE.findall(path)
    cur = record
    for key, idx in tokens:
        if key:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        else:
            i = int(idx)
            if not isinstance(cur, list) or i >= len(cur):
                return None
            cur = cur[i]
    return cur


_NORMALIZERS = {
    "E.164": lambda v: v,  # phones already normalized upstream; placeholder for chained config normalize
    "lower": lambda v: v.lower() if isinstance(v, str) else v,
    "upper": lambda v: v.upper() if isinstance(v, str) else v,
    "strip": lambda v: v.strip() if isinstance(v, str) else v,
}


def apply_config(record, config):
    """config = {
      "fields": [ {"path": "<canonical path>", "type": "...", "required": bool,
                    "from": "<override path>", "normalize": "<name>"} ],
      "include_confidence": bool,
      "on_missing": "null" | "omit" | "error"
    }
    Returns (output_dict, errors)
    """
    on_missing = config.get("on_missing", "null")
    errors = []
    out = {}

    for fdef in config.get("fields", []):
        out_path = fdef["path"]
        src_path = fdef.get("from", out_path)
        value = _get_path(record, src_path)

        if fdef.get("normalize") and value is not None:
            fn = _NORMALIZERS.get(fdef["normalize"])
            if fn:
                value = fn(value)

        if value is None:
            if fdef.get("required"):
                msg = f"required field '{out_path}' missing (source path '{src_path}')"
                if on_missing == "error":
                    errors.append(msg)
                    continue
                elif on_missing == "omit":
                    continue
                else:
                    out[out_path] = None
            else:
                if on_missing == "omit":
                    continue
                out[out_path] = None
        else:
            out[out_path] = value

    if config.get("include_confidence", True):
        out["overall_confidence"] = record.get("overall_confidence")
        out["provenance"] = record.get("provenance", [])

    return out, errors
