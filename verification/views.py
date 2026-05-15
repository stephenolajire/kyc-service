import logging

from django.conf import settings
from rapidfuzz import fuzz
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .utils.document_authenticity import assess_id_authenticity
from .utils.ocr import extract_text_from_id

logger = logging.getLogger(__name__)


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class VerifyView(APIView):
    def post(self, request):
        secret = request.data.get("secret")
        if secret != settings.KYC_SERVICE_SECRET:
            return Response(
                {"detail": "Unauthorized."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        full_name = request.data.get("full_name", "").strip()
        id_image = request.FILES.get("id_image")
        selfie = request.FILES.get("selfie")

        if not full_name or not id_image or not selfie:
            return Response(
                {"detail": "full_name, id_image and selfie are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        oversized_files = [
            field
            for field, uploaded in (("id_image", id_image), ("selfie", selfie))
            if uploaded.size and uploaded.size > settings.MAX_UPLOAD_BYTES
        ]
        if oversized_files:
            return Response(
                {
                    "detail": (
                        f"{', '.join(oversized_files)} exceeds the "
                        f"{settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."
                    )
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        id_bytes = id_image.read()
        selfie_bytes = selfie.read()

        authenticity = assess_id_authenticity(id_bytes)
        logger.info(
            "[KYC-SERVICE] ID authenticity score: %s, signals: %s",
            authenticity["score"],
            authenticity["signals"],
        )

        if authenticity["score"] < settings.ID_AUTHENTICITY_MIN_SCORE:
            return Response({
                "success": False,
                "step": "id_authenticity",
                "detail": (
                    "The ID image looks suspicious or edited. Please upload a clear, "
                    "uncropped photo of the original physical ID."
                ),
                "id_authenticity": authenticity,
            })

        try:
            ocr_result = extract_text_from_id(id_bytes)
            extracted_name = ocr_result.get("name", "").strip()
            logger.info("[KYC-SERVICE] OCR extracted: '%s'", extracted_name)
        except Exception as exc:
            logger.error("[KYC-SERVICE] OCR error: %s", exc)
            return Response(
                {"detail": f"OCR processing failed: {str(exc)}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if not extracted_name:
            return Response({
                "success": False,
                "step": "ocr",
                "detail": "Could not extract a name from the ID. Ensure the image is clear and well-lit.",
                "id_authenticity": authenticity,
            })

        name_score = fuzz.token_sort_ratio(
            extracted_name.lower(),
            full_name.lower(),
        )
        logger.info("[KYC-SERVICE] Name match score: %s/100", name_score)

        if name_score < settings.NAME_MATCH_THRESHOLD:
            return Response({
                "success": False,
                "step": "name_match",
                "detail": (
                    f"Name on ID ('{extracted_name}') does not match "
                    f"registered name ('{full_name}'). Score: {name_score}/100."
                ),
                "extracted_name": extracted_name,
                "name_match_score": name_score,
                "id_authenticity": authenticity,
            })

        try:
            from .utils.face_match import compare_faces

            face_result = compare_faces(
                id_bytes,
                selfie_bytes,
                tolerance=settings.FACE_TOLERANCE,
            )
            logger.info(
                "[KYC-SERVICE] Face distance: %s, match: %s",
                face_result["distance"],
                face_result["is_match"],
            )
        except ValueError as exc:
            return Response({
                "success": False,
                "step": "face_detection",
                "detail": str(exc),
                "id_authenticity": authenticity,
            })
        except Exception as exc:
            logger.error("[KYC-SERVICE] Face match error: %s", exc)
            return Response(
                {"detail": f"Face matching failed: {str(exc)}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if not face_result["is_match"]:
            return Response({
                "success": False,
                "step": "face_match",
                "detail": (
                    f"Selfie does not match the face on your ID. "
                    f"Confidence: {face_result['confidence']}%."
                ),
                "face_distance": face_result["distance"],
                "face_confidence": face_result["confidence"],
                "id_authenticity": authenticity,
            })

        return Response({
            "success": True,
            "extracted_name": extracted_name,
            "name_match_score": round(name_score / 100, 4),
            "face_distance": face_result["distance"],
            "face_confidence": face_result["confidence"],
            "id_authenticity": authenticity,
        })
