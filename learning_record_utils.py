import json
import re


def normalize_poem_name(name: str) -> str:
    """Normalize model/retrieval poem titles for learning-record matching."""
    normalized = str(name or "").strip()
    if "《" in normalized and "》" in normalized:
        normalized = normalized.split("《", 1)[1].split("》", 1)[0]
    else:
        normalized = normalized.split(" ", 1)[0]
    return normalized.strip("《》 \t\r\n")


def parse_learning_marker(answer: str) -> tuple[str, dict]:
    """
    Parse the hidden learning marker from a model answer.

    Preferred format:
      <!-- learning: {"explained":["静夜思"],"mentioned":["春晓"],"no_match":false} -->

    The old <!-- taught: ... --> marker is still accepted for compatibility.
    """
    learning = {"explained": [], "mentioned": [], "no_match": False}

    marker_pat = r"<!--\s*learning:\s*(\{.*?\})\s*-->"
    marker_match = re.search(marker_pat, answer, flags=re.DOTALL)
    if marker_match:
        try:
            data = json.loads(marker_match.group(1))
            explained = data.get("explained", [])
            mentioned = data.get("mentioned", [])
            learning = {
                "explained": [str(name).strip() for name in explained if str(name).strip()],
                "mentioned": [str(name).strip() for name in mentioned if str(name).strip()],
                "no_match": bool(data.get("no_match", False)),
            }
        except (TypeError, json.JSONDecodeError):
            learning = {"explained": [], "mentioned": [], "no_match": False}

        clean = re.sub(marker_pat, "", answer, flags=re.DOTALL).strip()
        return clean, learning

    taught_pat = r"<!--\s*taught:\s*(.*?)-->"
    taught_match = re.search(taught_pat, answer, flags=re.DOTALL)
    if taught_match:
        raw = taught_match.group(1).strip()
        names = [name.strip() for name in re.split(r"[,，、;\n]+", raw) if name.strip()]
        clean = re.sub(taught_pat, "", answer, flags=re.DOTALL).strip()
        return clean, {"explained": names, "mentioned": [], "no_match": False}

    return answer, learning


def _split_tags(tags_text: str) -> list[str]:
    tags = []
    seen_tags = set()
    for tag in str(tags_text or "").split("、"):
        tag = tag.strip()
        if tag and tag not in seen_tags:
            seen_tags.add(tag)
            tags.append(tag)
    return tags


def _poem_entry(item: dict) -> dict:
    return {
        "title": str(item.get("title", "")).strip(),
        "tags": _split_tags(item.get("tags", "")),
    }


def _build_poem_lookup(poem_catalog: list, search_results: list) -> dict:
    lookup = {}
    for item in list(poem_catalog or []) + list(search_results or []):
        title = str(item.get("title", "")).strip()
        if title:
            lookup.setdefault(normalize_poem_name(title), _poem_entry(item))
    return lookup


def _resolve_poem_names(names: list, lookup: dict) -> list:
    resolved = []
    seen = set()
    for name in names:
        key = normalize_poem_name(name)
        if not key or key in seen or key not in lookup:
            continue
        seen.add(key)
        resolved.append(lookup[key])
    return resolved


def build_interaction_payload(
    search_results: list,
    poem_catalog: list,
    learned_titles: set,
    learning_marker: dict,
) -> dict:
    """
    Build the long-term learning record payload.

    Candidate poems are stored for traceability but never counted as learned.
    Explained poems count as new learning unless the title was already learned,
    in which case they count as review. Mentioned poems are stored separately.
    """
    lookup = _build_poem_lookup(poem_catalog, search_results)
    learned_keys = {normalize_poem_name(title) for title in learned_titles or set()}

    candidate_poems = [_poem_entry(item) for item in search_results if str(item.get("title", "")).strip()]
    explained_candidates = _resolve_poem_names(learning_marker.get("explained", []), lookup)
    mentioned_candidates = _resolve_poem_names(learning_marker.get("mentioned", []), lookup)

    explained_poems = []
    reviewed_poems = []
    explained_keys = set()
    for poem in explained_candidates:
        key = normalize_poem_name(poem["title"])
        explained_keys.add(key)
        if key in learned_keys:
            reviewed_poems.append(poem)
        else:
            explained_poems.append(poem)

    mentioned_poems = [
        poem for poem in mentioned_candidates
        if normalize_poem_name(poem["title"]) not in explained_keys
    ]

    if explained_poems and reviewed_poems:
        record_type = "mixed"
    elif explained_poems:
        record_type = "explained"
    elif reviewed_poems:
        record_type = "reviewed"
    elif mentioned_poems:
        record_type = "mentioned"
    else:
        record_type = "no_match"

    return {
        "record_type": record_type,
        "explained_poems": explained_poems,
        "reviewed_poems": reviewed_poems,
        "mentioned_poems": mentioned_poems,
        "candidate_poems": candidate_poems,
    }
