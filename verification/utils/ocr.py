from django.conf import settings

_reader = None


def get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


def extract_text_from_id(image_bytes: bytes) -> dict:
    import cv2
    import numpy as np

    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode ID image.")

    max_dim = settings.MAX_IMAGE_DIMENSION
    h, w = image.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        image = cv2.resize(image, (int(w * scale), int(h * scale)))

    results = get_reader().readtext(image, paragraph=False)
    full_text = "\n".join([text for (_, text, _) in results])

    return {
        "full_text": full_text,
        "name": extract_name_from_text(full_text),
    }


def extract_name_from_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    name_keywords = ["surname", "first name", "firstname", "full name", "name", "given name"]
    collected = []

    for i, line in enumerate(lines):
        lower = line.lower()
        for kw in name_keywords:
            if kw in lower:
                after_colon = line.split(":")[-1].strip()
                if after_colon and not any(k in after_colon.lower() for k in name_keywords):
                    collected.append(after_colon)
                elif i + 1 < len(lines):
                    collected.append(lines[i + 1])
                break

    return " ".join(collected[:2]).strip()
