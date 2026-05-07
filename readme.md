markdown

# KYC Verification Microservice

A standalone Django REST Framework microservice that handles identity verification for the Fixora platform. It performs OCR text extraction from government-issued ID documents, fuzzy name matching against a registered name, and deep learning face comparison between the ID photo and a selfie.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running Locally](#running-locally)
- [API Reference](#api-reference)
  - [Health Check](#health-check)
  - [Verify Identity](#verify-identity)
- [Verification Pipeline](#verification-pipeline)
  - [Step 1 — OCR Name Extraction](#step-1--ocr-name-extraction)
  - [Step 2 — Name Matching](#step-2--name-matching)
  - [Step 3 — Face Matching](#step-3--face-matching)
- [Security](#security)
- [Accuracy & Thresholds](#accuracy--thresholds)
- [Error Responses](#error-responses)
- [Deployment](#deployment)
  - [Render](#render)
  - [Environment Variables on Render](#environment-variables-on-render)
- [Integration with Main App](#integration-with-main-app)
- [Troubleshooting](#troubleshooting)

---

## Overview

The KYC (Know Your Customer) service is intentionally kept as a **separate, stateless microservice** to:

- Isolate heavy ML dependencies (TensorFlow, DeepFace, EasyOCR) from the main Django app
- Allow independent scaling of the verification workload
- Keep the main app lightweight and fast
- Enable independent redeployment without affecting the core API

The service is **stateless** — it receives images, processes them, and returns a JSON result. It does not store anything. All persistence (saving results, uploading selfies to Cloudinary) is handled by the main app's Celery worker after receiving the response.

---

## Architecture

```
Mobile App
    │
    │  POST /kyc/submit/  (id_image + selfie)
    ▼
Main Django API  ──────────────────────────────────────────────────────────
    │                                                                      │
    │  Returns 202 immediately                                             │
    │  Saves temp images to DB                                             │
    │  Queues background task                                              │
    ▼                                                                      │
Celery Worker                                                              │
    │                                                                      │
    │  POST /verify/  (full_name + id_image + selfie + secret)            │
    ▼                                                                      │
KYC Microservice  (this service) ◄─────────────────────────────────────────
    │
    │  1. OCR  →  extract name from ID
    │  2. Fuzzy match name against registered full_name
    │  3. DeepFace  →  compare face on ID vs selfie
    │
    │  Returns JSON { success, extracted_name, scores, ... }
    ▼
Celery Worker
    │
    │  Saves result to DB
    │  Uploads selfie to Cloudinary
    │  Sets user.is_kyc_verified = True
    ▼
Database updated
```

---

## Tech Stack

| Component | Library | Purpose |
|---|---|---|
| Web framework | Django 6 + DRF | API endpoints |
| OCR | EasyOCR | Extract text from ID images |
| Face matching | DeepFace (VGG-Face) | Compare faces |
| Name matching | RapidFuzz | Fuzzy string comparison |
| Image processing | OpenCV, Pillow | Image decoding and prep |
| Server | Gunicorn | Production WSGI server |

---

## Project Structure

```
kyc-service/
├── config/
│   ├── __init__.py
│   ├── settings.py          # Django settings
│   ├── urls.py              # Root URL config
│   └── wsgi.py              # WSGI entry point
├── verification/
│   ├── __init__.py
│   ├── views.py             # VerifyView + HealthView
│   ├── urls.py              # App URL config
│   └── utils/
│       ├── __init__.py
│       ├── ocr.py           # EasyOCR text extraction
│       └── face_match.py    # DeepFace comparison
├── manage.py
├── requirements.txt
├── Procfile                 # For Render deployment
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- pip
- Virtual environment (recommended)

> **Note:** The first run will automatically download model weights for EasyOCR (~100MB) and DeepFace VGG-Face (~500MB). Ensure you have a stable internet connection.

### Installation

```bash
# Clone the repo
git clone https://github.com/your-org/kyc-service.git
cd kyc-service

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / Mac
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-django-secret-key-any-random-string
DEBUG=True
KYC_SERVICE_SECRET=your-shared-secret-same-as-main-app
```

> `KYC_SERVICE_SECRET` must be **identical** to the `KYC_SERVICE_SECRET` set in your main Django app. This is how the microservice authenticates incoming requests.

### Running Locally

```bash
python manage.py runserver 8001
```

The service will be available at `http://127.0.0.1:8001`.

In your main app's local `.env`, set:

```env
KYC_SERVICE_URL=http://127.0.0.1:8001
KYC_SERVICE_SECRET=your-shared-secret
```

---

## API Reference

### Health Check

Check that the service is running.

```
GET /health/
```

**Response**

```json
{
  "status": "ok"
}
```

---

### Verify Identity

The main verification endpoint. Accepts multipart form data.

```
POST /verify/
Content-Type: multipart/form-data
```

**Request Fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `full_name` | string | ✓ | The user's registered full name to match against |
| `id_image` | file | ✓ | Photo of a government-issued ID document |
| `selfie` | file | ✓ | Front-facing selfie photo of the user |
| `secret` | string | ✓ | Shared secret key for request authentication |

**Accepted ID Types**

- NIN slip
- Voter's card
- Driver's licence
- International passport
- Any government-issued ID with a name and photo

**Success Response** `200 OK`

```json
{
  "success": true,
  "extracted_name": "JOHN DOE",
  "name_match_score": 0.97,
  "face_distance": 0.312,
  "face_confidence": 68.8
}
```

**Failure Response — OCR failed** `200 OK`

```json
{
  "success": false,
  "step": "ocr",
  "detail": "Could not extract a name from the ID. Ensure the image is clear and well-lit."
}
```

**Failure Response — Name mismatch** `200 OK`

```json
{
  "success": false,
  "step": "name_match",
  "detail": "Name on ID ('JANE DOE') does not match registered name ('John Doe'). Score: 42/100.",
  "extracted_name": "JANE DOE",
  "name_match_score": 42
}
```

**Failure Response — Face mismatch** `200 OK`

```json
{
  "success": false,
  "step": "face_match",
  "detail": "Selfie does not match the face on your ID. Confidence: 28.5%.",
  "face_distance": 0.715,
  "face_confidence": 28.5
}
```

**Failure Response — Face not detected** `200 OK`

```json
{
  "success": false,
  "step": "face_detection",
  "detail": "No face detected in image."
}
```

**Error Response — Unauthorized** `401 Unauthorized`

```json
{
  "detail": "Unauthorized."
}
```

**Error Response — Missing fields** `400 Bad Request`

```json
{
  "detail": "full_name, id_image and selfie are required."
}
```

**Error Response — Processing error** `422 Unprocessable Entity`

```json
{
  "detail": "OCR processing failed: "
}
```

> **Note:** Verification failures (name mismatch, face mismatch etc.) return `200 OK` with `success: false`. Only server-side errors return `4xx/5xx`. This is intentional — the Celery worker treats non-2xx as retryable errors, while `success: false` is a definitive user-facing failure.

---

## Verification Pipeline

### Step 1 — OCR Name Extraction

Uses **EasyOCR** to extract all text from the ID image, then applies heuristic parsing to find the name fields.

```python
# Looks for lines following keywords:
name_keywords = ["surname", "first name", "firstname", "full name", "name", "given name"]
```

The parser looks for a colon-separated value on the same line, or the line immediately following the keyword. It collects up to two name parts (surname + first name) and joins them.

**Tips for best OCR results:**
- ID must be photographed flat with no bending
- All four corners must be visible in the frame
- Lighting must be even — no glare or heavy shadows
- Minimum recommended resolution: 1080p

---

### Step 2 — Name Matching

Uses **RapidFuzz** `token_sort_ratio` to compare the extracted name against the registered `full_name`. This method:

- Is case-insensitive
- Handles reordered name tokens (e.g. "Doe John" vs "John Doe")
- Tolerates minor OCR errors and typos
- Scores from 0 to 100

```
Default threshold: 75/100

Examples:
  "JOHN DOE"  vs "John Doe"     → 100  ✓ pass
  "JOHN A DOE" vs "John Doe"    →  89  ✓ pass
  "JANE DOE"  vs "John Doe"     →  50  ✗ fail
```

---

### Step 3 — Face Matching

Uses **DeepFace** with the **VGG-Face** model and **cosine distance** metric to compare the face on the ID document against the selfie.

```
Model:          VGG-Face
Metric:         Cosine distance  (range: 0.0 – 1.0)
Threshold:      0.68  (DeepFace's own calibrated default)

Distance interpretation:
  0.0 – 0.40  →  Very high confidence match
  0.40 – 0.68 →  Acceptable match  ✓
  0.68+        →  No match          ✗
```

DeepFace's `verify()` method is used directly rather than manually computing distance — this ensures the model's own internally calibrated threshold is applied consistently.

**Requirements for reliable face matching:**
- Face must be clearly visible on both the ID and selfie
- Selfie should be taken in good, even lighting
- Face should be front-facing, not angled
- No sunglasses, masks, or heavy filters

---

## Security

### Shared Secret Authentication

The service does not use JWT or session-based auth. Instead, it uses a **shared secret** passed as a form field with every request. Only the main app (which knows the secret) can call this service.

```python
secret = request.data.get("secret")
if secret != settings.KYC_SERVICE_SECRET:
    return Response({"detail": "Unauthorized."}, status=401)
```

**Best practices:**
- Use a long random string (32+ characters) as the secret
- Never expose `KYC_SERVICE_SECRET` in client-side code or logs
- Rotate the secret periodically and update both services

### No Data Persistence

This service is **completely stateless**. It:
- Does not write to any database
- Does not store uploaded images
- Does not log image content
- Processes everything in memory and discards it after the response

### Network Isolation

On Render, use the **Internal URL** (not the public URL) for communication between your main app and this service. Internal URLs are only accessible within Render's private network:

```env
# Use internal URL in production (faster + more secure)
KYC_SERVICE_URL=https://kyc-service-internal.onrender.com

# Public URL only needed for external testing
KYC_SERVICE_URL=https://kyc-service.onrender.com
```

---

## Accuracy & Thresholds

| Check | Method | Default Threshold | Accuracy |
|---|---|---|---|
| OCR extraction | EasyOCR | — | ~85–92% on clear IDs |
| Name matching | RapidFuzz token_sort_ratio | 75/100 | Very reliable with good OCR |
| Face detection | DeepFace MTCNN | — | ~95%+ |
| Face matching | VGG-Face cosine | 0.68 | ~97–99% |

**Adjusting thresholds** in `config/settings.py`:

```python
FACE_TOLERANCE = 0.68      # Lower = stricter face match
NAME_MATCH_THRESHOLD = 75  # Lower = more lenient name match
```

---

## Error Responses

| Scenario | HTTP Status | `success` field |
|---|---|---|
| Wrong secret | `401` | — |
| Missing fields | `400` | — |
| OCR library crash | `422` | — |
| Face match library crash | `422` | — |
| Name not found in ID | `200` | `false` |
| Name score below threshold | `200` | `false` |
| No face detected | `200` | `false` |
| Multiple faces detected | `200` | `false` |
| Face distance above threshold | `200` | `false` |
| All checks passed | `200` | `true` |

---

## Deployment

### Render

**`Procfile`** (project root):

```
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 2
```

> `--timeout 120` is required. DeepFace and EasyOCR load ML models on the first request which can take 20–40 seconds. Without an increased timeout Gunicorn will kill the worker before it finishes loading.

**Steps:**

1. Push the `kyc-service` repo to GitHub
2. Go to **Render Dashboard → New → Web Service**
3. Connect the repo
4. Fill in:

| Field | Value |
|---|---|
| **Name** | `kyc-service` |
| **Environment** | `Python` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 2` |

5. Add environment variables (see below)
6. Deploy

> **Instance type:** Use at least a **Standard** instance on Render. The free tier does not have enough RAM to load TensorFlow + VGG-Face model weights (~1.5GB peak usage).

### Environment Variables on Render

| Key | Value |
|---|---|
| `SECRET_KEY` | Any long random string |
| `DEBUG` | `False` |
| `KYC_SERVICE_SECRET` | Same secret as your main app |

---

## Integration with Main App

### Required settings in main app

```python
# config/settings.py
KYC_SERVICE_URL = config("KYC_SERVICE_URL")
KYC_SERVICE_SECRET = config("KYC_SERVICE_SECRET")
```

### Required env vars in main app

```env
KYC_SERVICE_URL=https://your-kyc-service.onrender.com
KYC_SERVICE_SECRET=your-shared-secret
```

### How the main app calls this service

The Celery worker in the main app sends a `multipart/form-data` POST request using `httpx`:

```python
with httpx.Client(timeout=120.0) as client:
    response = client.post(
        f"{settings.KYC_SERVICE_URL}/verify/",
        data={
            "full_name": user.full_name,
            "secret": settings.KYC_SERVICE_SECRET,
        },
        files={
            "id_image": ("id_image.jpg", id_bytes, "image/jpeg"),
            "selfie": ("selfie.jpg", selfie_bytes, "image/jpeg"),
        },
    )
```

### Response handling in main app

```python
result = response.json()

if not result.get("success"):
    # Mark KYC as failed with the reason from the service
    fail(result.get("detail", "Verification failed."))
    return

# All passed — save results
kyc.extracted_name = result["extracted_name"]
kyc.name_match_score = result["name_match_score"]
kyc.face_match_distance = result["face_distance"]
```

---

## Troubleshooting

### Service times out on first request

**Cause:** DeepFace and EasyOCR download and load model weights on first use (~500MB).

**Fix:** Increase Gunicorn timeout to 120+ seconds. On Render, the first cold start after a deploy will be slow — subsequent requests are fast.

```
gunicorn config.wsgi:application --timeout 120
```

---

### `No face detected in image`

**Cause:** The ID photo or selfie does not have a clearly visible face, or the image quality is too low.

**Fix:** Ensure:
- The ID photo includes the photo section of the ID
- The selfie is well-lit and front-facing
- Images are at least 480×480px

---

### `Could not extract a name from the ID`

**Cause:** EasyOCR could not read text clearly, or the ID layout does not match expected keyword patterns.

**Fix:**
- Ensure all four corners of the ID are visible
- Avoid glare, shadows, and blurry images
- The ID must be in English or have English transliteration

---

### Name match fails for valid users

**Cause:** The registered name differs significantly from how it appears on the ID (e.g. middle name included on ID but not registered).

**Fix:** Lower the `NAME_MATCH_THRESHOLD` in `settings.py` from `75` to `65`:

```python
NAME_MATCH_THRESHOLD = 65
```

---

### `OSError` or `PermissionError` on Windows (local dev)

**Cause:** Celery's default prefork pool uses Unix semaphores which are not supported on Windows.

**Fix:** Run the Celery worker with `--pool=solo`:

```bash
celery -A config worker --loglevel=info --pool=solo
```

This does not affect production (Render runs Linux).

---

### Stale tasks with wrong name in Redis queue

**Cause:** Task was queued under an old name (e.g. `verification.tasks.process_kyc`) before the app was renamed.

**Fix:** Purge the queue to clear stale tasks:

```bash
celery -A config purge
```

Type `y` to confirm, then restart the worker.
