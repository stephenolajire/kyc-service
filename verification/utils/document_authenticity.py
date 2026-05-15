import io
import math

from PIL import ExifTags, Image

SUSPICIOUS_SOFTWARE_MARKERS = (
    "adobe",
    "photoshop",
    "lightroom",
    "gimp",
    "canva",
    "midjourney",
    "dall-e",
    "stable diffusion",
    "firefly",
    "bing image creator",
)


def _decode_image(image_bytes: bytes):
    import cv2
    import numpy as np

    nparr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


def _metadata_flags(image_bytes: bytes):
    flags = []
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            exif = image.getexif()
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id)).lower()
                value_text = str(value).lower()
                if tag in {"software", "processingsoftware"}:
                    for marker in SUSPICIOUS_SOFTWARE_MARKERS:
                        if marker in value_text:
                            flags.append(f"metadata references {marker}")
                            break
    except Exception:
        return flags
    return flags


def _laplacian_variance(gray):
    import cv2

    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _entropy(gray):
    import cv2

    histogram = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
    probabilities = histogram / max(histogram.sum(), 1)
    return -sum(p * math.log2(p) for p in probabilities if p > 0)


def _edge_density(gray):
    import cv2
    import numpy as np

    edges = cv2.Canny(gray, 80, 180)
    return float(np.count_nonzero(edges) / edges.size)


def _ela_score(image):
    import cv2

    _, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    recompressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(image, recompressed)
    return float(diff.mean()), float(diff.std())


def assess_id_authenticity(image_bytes: bytes) -> dict:
    import cv2

    image = _decode_image(image_bytes)
    if image is None:
        return {
            "score": 0,
            "is_suspicious": True,
            "signals": ["image could not be decoded"],
            "metrics": {},
        }

    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = _laplacian_variance(gray)
    entropy = _entropy(gray)
    edge_density = _edge_density(gray)
    ela_mean, ela_std = _ela_score(image)

    score = 100
    signals = []

    if min(h, w) < 450:
        score -= 20
        signals.append("image resolution is too low for reliable document checks")

    if blur < 35:
        score -= 18
        signals.append("document image is very blurry")

    if entropy < 4.0:
        score -= 15
        signals.append("image has unusually low visual detail")
    elif entropy > 7.8:
        score -= 10
        signals.append("image has unusually high noise or texture")

    if edge_density < 0.025:
        score -= 12
        signals.append("document has too few edges for printed ID content")

    if ela_mean > 12 and ela_std > 18:
        score -= 22
        signals.append("compression differences suggest possible image editing")

    metadata_signals = _metadata_flags(image_bytes)
    if metadata_signals:
        score -= 25
        signals.extend(metadata_signals)

    score = max(0, min(100, score))

    return {
        "score": score,
        "is_suspicious": score < 55,
        "signals": signals,
        "metrics": {
            "width": w,
            "height": h,
            "blur": round(blur, 2),
            "entropy": round(entropy, 2),
            "edge_density": round(edge_density, 4),
            "ela_mean": round(ela_mean, 2),
            "ela_std": round(ela_std, 2),
        },
    }
