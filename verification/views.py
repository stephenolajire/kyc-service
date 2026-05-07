import logging
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rapidfuzz import fuzz

from .utils.ocr import extract_text_from_id
from .utils.face_match import compare_faces

logger = logging.getLogger(__name__)


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class VerifyView(APIView):

    def post(self, request):
        # ── Auth: shared secret check ───────────────────────────────────
        secret = request.data.get("secret")
        if secret != settings.KYC_SERVICE_SECRET:
            return Response(
                {"detail": "Unauthorized."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ── Validate inputs ─────────────────────────────────────────────
        full_name = request.data.get("full_name", "").strip()
        id_image = request.FILES.get("id_image")
        selfie = request.FILES.get("selfie")

        if not full_name or not id_image or not selfie:
            return Response(
                {"detail": "full_name, id_image and selfie are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        id_bytes = id_image.read()
        selfie_bytes = selfie.read()

        # ── Step 1: OCR ─────────────────────────────────────────────────
        try:
            ocr_result = extract_text_from_id(id_bytes)
            extracted_name = ocr_result.get("name", "").strip()
            logger.info(f"[KYC-SERVICE] OCR extracted: '{extracted_name}'")
        except Exception as exc:
            logger.error(f"[KYC-SERVICE] OCR error: {exc}")
            return Response(
                {"detail": f"OCR processing failed: {str(exc)}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if not extracted_name:
            return Response({
                "success": False,
                "step": "ocr",
                "detail": "Could not extract a name from the ID. Ensure the image is clear and well-lit.",
            })

        # ── Step 2: Name match ──────────────────────────────────────────
        name_score = fuzz.token_sort_ratio(
            extracted_name.lower(),
            full_name.lower(),
        )
        logger.info(f"[KYC-SERVICE] Name match score: {name_score}/100")

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
            })

        # ── Step 3: Face match ──────────────────────────────────────────
        try:
            face_result = compare_faces(
                id_bytes,
                selfie_bytes,
                tolerance=settings.FACE_TOLERANCE,
            )
            logger.info(f"[KYC-SERVICE] Face distance: {face_result['distance']}, match: {face_result['is_match']}")
        except ValueError as exc:
            # Face not found / multiple faces — user error
            return Response({
                "success": False,
                "step": "face_detection",
                "detail": str(exc),
            })
        except Exception as exc:
            logger.error(f"[KYC-SERVICE] Face match error: {exc}")
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
            })

        # ── All passed ──────────────────────────────────────────────────
        return Response({
            "success": True,
            "extracted_name": extracted_name,
            "name_match_score": round(name_score / 100, 4),
            "face_distance": face_result["distance"],
            "face_confidence": face_result["confidence"],
        })