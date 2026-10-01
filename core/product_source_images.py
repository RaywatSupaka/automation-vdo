"""Conservative, non-destructive selection of product references."""
import hashlib
from pathlib import Path, PurePosixPath
from PIL import Image

# User-confirmed separate Shopee promotion layer; decoded pixels avoid PNG
# metadata/recompression differences. Never generalize this to all PNG/alpha.
KNOWN_PROMOTION_PIXELS = {
    "2149f40f1af0640b0986d8633f6358ecda73444b323058f92dbe702833c56a1b",
}


def canonical_source_image_paths(folder, paths):
    """Read old root-relative Shopee captures as job-relative image paths.

    Earlier imports saved ``JOB-id/original/file`` even though every reader
    resolves paths inside the already-selected JOB directory. Only collapse
    that exact legacy shape when its real file is inside this same job.
    This is read-only; saved images and unrelated path fields stay untouched.
    """
    folder = Path(folder).resolve()
    original = (folder / "original").resolve()
    normalized = []
    for value in paths or []:
        relative = str(value or "").strip().replace("\\", "/")
        parts = PurePosixPath(relative).parts
        if len(parts) == 3 and parts[0] == folder.name and parts[1] == "original":
            candidate = (original / parts[2]).resolve()
            if original.parent == folder and candidate.parent == original and candidate.is_file():
                relative = f"original/{parts[2]}"
        normalized.append(relative)
    return normalized


def verified_source_image_paths(folder, paths):
    """Return canonical paths that are safe, present, and readable images."""
    folder = Path(folder).resolve()
    accepted = []
    for relative in canonical_source_image_paths(folder, paths):
        try:
            candidate = (folder / relative).resolve()
            if folder not in candidate.parents or not candidate.is_file():
                continue
            with Image.open(candidate) as image:
                image.verify()
            accepted.append(relative)
        except Exception:
            continue
    return accepted


def inspect_source_image(path, metadata=None):
    metadata = metadata if isinstance(metadata, dict) else {}
    with Image.open(path) as image:
        image.load()
        rgba = image.convert("RGBA")
    digest = hashlib.sha256(rgba.tobytes()).hexdigest()
    alpha = rgba.getchannel("A")
    transparent = alpha.histogram()[0] / (rgba.width * rgba.height)
    bounds = alpha.getbbox()
    result = {"decision": "accept", "reason": "product_reference", "sha256": digest,
              "transparent_fraction": round(transparent, 4), "bounds": bounds}
    if digest in KNOWN_PROMOTION_PIXELS:
        result.update(decision="exclude", reason="confirmed_shopee_promotion_overlay")
    elif bounds is None:
        result.update(decision="exclude", reason="empty_transparent_image")
    elif transparent > .80 and bounds[1] >= rgba.height * .70 and bounds[3] - bounds[1] <= rgba.height * .30:
        # Sparse edge graphics alone are ambiguous: a real small product may
        # be photographed off-centre. Exclude only with independent DOM proof.
        proven_layer = metadata.get("decorative_layer") is True and metadata.get("overlaps_product") is True
        result.update(decision="exclude" if proven_layer else "review",
                      reason="promotion_overlay" if proven_layer else "sparse_edge_image_needs_review")
    return result


def select_source_images(folder, paths, metadata=None):
    folder = Path(folder).resolve()
    accepted, decisions, seen = [], [], set()
    original_paths = list(paths or [])
    for original_relative, relative in zip(original_paths, canonical_source_image_paths(folder, original_paths)):
        path = (folder / str(relative)).resolve()
        if folder not in path.parents or not path.is_file():
            decisions.append({"path": str(relative), "decision": "review", "reason": "invalid_or_missing_image"})
            continue
        try:
            info = inspect_source_image(path, (metadata or {}).get(str(relative)) or (metadata or {}).get(str(original_relative)))
        except Exception:
            info = {"decision": "review", "reason": "unreadable_image"}
        info["path"] = str(relative)
        if info["decision"] == "accept":
            if info["sha256"] in seen:
                info.update(decision="exclude", reason="duplicate_product_image")
            else:
                accepted.append(str(relative))
                seen.add(info["sha256"])
        decisions.append(info)
    return accepted, decisions
