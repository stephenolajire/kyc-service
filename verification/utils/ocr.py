import easyocr
import numpy as np
import cv2


def extract_text_from_id(image_bytes: bytes) -> dict:
    # gpu=False — no GPU on Render, saves memory trying to init CUDA
    # paragraph=False — faster, less memory
    reader = easyocr.Reader(["en"], gpu=False)

    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Resize large images before OCR — cuts memory usage significantly
    max_dim = 1200
    h, w = image.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        image = cv2.resize(image, (int(w * scale), int(h * scale)))

    results = reader.readtext(image, paragraph=False)
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