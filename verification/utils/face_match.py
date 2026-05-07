from deepface import DeepFace
from PIL import Image
import tempfile
import os
import io


def load_image_from_bytes(image_bytes: bytes) -> str:
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    pil_image.save(temp_file.name, format="JPEG")
    temp_file.close()
    return temp_file.name


def compare_faces(id_image_bytes: bytes, selfie_bytes: bytes, tolerance: float = 0.68) -> dict:
    id_temp = load_image_from_bytes(id_image_bytes)
    selfie_temp = load_image_from_bytes(selfie_bytes)

    try:
        result = DeepFace.verify(
            img1_path=id_temp,
            img2_path=selfie_temp,
            model_name="VGG-Face",
            distance_metric="cosine",
            enforce_detection=True,
        )
    finally:
        for path in [id_temp, selfie_temp]:
            if os.path.exists(path):
                os.remove(path)

    distance = result["distance"]
    is_match = result["verified"]
    confidence = round((1 - distance) * 100, 2)

    return {
        "is_match": is_match,
        "distance": round(distance, 4),
        "confidence": confidence,
    }