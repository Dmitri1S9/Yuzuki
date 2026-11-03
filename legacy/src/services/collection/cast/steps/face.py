"""Face detection + centered square crop for stage 1 character portraits.
Called from the @verified_portrait decorator in images.py so a raw
web-search image is never stored without a validated single face — zero
faces (wrong/generic image) or more than one (group shot) both get
rejected, and the caller tries the next search candidate instead.

Every character here is a drawn anime/manga character, not a photographed
human — confirmed live that this matters: OpenCV's bundled
haarcascade_frontalface_default (trained on photographic faces) either
missed or false-positived on real official character art (e.g. finding a
"face" in a logo near the bottom of a portrait). lbpcascade_animeface
(nagadomi, MIT-licensed, https://github.com/nagadomi/lbpcascade_animeface)
is a small cascade purpose-trained on anime faces and correctly found
exactly one face on the same images — bundled locally in models/ rather
than opencv-python-headless's built-in cascades, and rather than fetched
at runtime (no network dependency for a correctness-critical check).
"""
import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_CASCADE_PATH = Path(__file__).parent / "models" / "lbpcascade_animeface.xml"
_CASCADE = cv2.CascadeClassifier(str(_CASCADE_PATH))

_MARGIN = 0.6  # fraction of the face box's own size added on each side before squaring
_MIN_CROP_SIZE = 200  # px — a confidently-detected face in a tiny source
                       # region (e.g. one inset headshot on a multi-view
                       # reference sheet) still crops down to a blurry,
                       # low-quality square if the detection box itself was
                       # small. Confirmed live: a correct, unambiguous
                       # detection produced a 170x169 output that looked
                       # like garbage once displayed larger. Detection
                       # confidence and output quality are two different
                       # checks — this rejects on the second even when the
                       # first already passed, same as the face-count
                       # check: don't accept a bad result just because
                       # nothing else about it look wrong.

# Strict first, ONE moderate fallback — not a ladder down to "find
# something, anything." minNeighbors is the detector's own vote count for a
# region (how many overlapping candidate windows agreed it's a face); at
# minNeighbors=1 a single real face can itself split into two adjacent
# weak, unconsolidated boxes, manufacturing the exact "2 faces" ambiguity
# this whole check exists to catch — that isn't detection anymore, it's
# accepting noise. minNeighbors=3 is confirmed live to still recover real
# misses (a standard 3-view character reference sheet, missed entirely at
# the strict tier) without that failure mode. A tier that finds >1 stops
# the search immediately — more relaxation only ever finds more candidates,
# never fewer. A case neither tier confidently resolves (confirmed live: an
# extreme close-up crop) is correctly left unresolved — the caller moves on
# to the next search candidate instead of a forced, low-confidence guess.
_DETECT_TIERS = [
    dict(scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)),
    dict(scaleFactor=1.05, minNeighbors=3, minSize=(30, 30)),
]


def _detect_faces(gray):
    for params in _DETECT_TIERS:
        faces = _CASCADE.detectMultiScale(gray, **params)
        if len(faces) > 0:
            return faces
    return []


def crop_to_face(image_bytes: bytes) -> bytes | None:
    """Returns a square JPEG crop centered on the single detected face, or
    None if zero or more than one face was found."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    faces = _detect_faces(gray)
    if len(faces) != 1:
        return None

    x, y, w, h = (int(v) for v in faces[0])
    cx, cy = x + w / 2, y + h / 2
    half = max(w, h) * (0.5 + _MARGIN)

    left, top = max(0.0, cx - half), max(0.0, cy - half)
    right, bottom = min(float(image.width), cx + half), min(float(image.height), cy + half)
    side = min(right - left, bottom - top)  # keep it square even where the margin clipped
    if side < _MIN_CROP_SIZE:
        return None
    left, top = min(left, right - side), min(top, bottom - side)

    cropped = image.crop((int(left), int(top), int(left + side), int(top + side)))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def center_crop_square(image_bytes: bytes) -> bytes | None:
    """Plain centered square crop, no face detection — for a source that
    already guarantees correct identity (AniList's own per-character
    artwork), where rejecting on a missed face (e.g. a side profile or
    stylized pose the cascade doesn't recognize) would throw away a known-
    correct image for no good reason. Not for unverified search results —
    those still go through crop_to_face, which can reject a wrong photo."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
    side = min(image.width, image.height)
    if side < _MIN_CROP_SIZE:
        return None
    left = (image.width - side) // 2
    top = 0  # bias to the top, not vertical-center — a portrait's face is
             # almost always in the upper portion of the source image
    cropped = image.crop((left, top, left + side, top + side))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
