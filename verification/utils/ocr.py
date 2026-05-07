import easyocr
import numpy as np
import cv2


def extract_text_from_id(image_bytes: bytes) -> dict:
    # Initialized inside function — safe for multiprocessing
    reader = easyocr.Reader(["en"], gpu=False)

    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    results = reader.readtext(image)
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
import easyocr
import numpy as np
import cv2


def extract_text_from_id(image_bytes: bytes) -> dict:
    # Initialized inside function — safe for multiprocessing
    reader = easyocr.Reader(["en"], gpu=False)

    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    results = reader.readtext(image)
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