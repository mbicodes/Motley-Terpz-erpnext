# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

"""Server-side check that a kiosk verification photo actually shows a face.

This is the backstop for the client-side face check in manufacturing-timesheet.html:
the browser already refuses to let Save & Start/End be pressed until its own live
face-detection sees a face in the video feed, but that is JavaScript running on a
device nobody at Motley controls end to end - a direct POST to start_session/
end_session (or a modified page) would skip it entirely. This module re-checks the
photo itself, server-side, so "no face, no clock-in/out" holds even then.

Detector: OpenCV's YuNet (``cv2.FaceDetectorYN``), a small (~230KB) ONNX face
detector bundled with this app under ``manufacturing_timesheet_kiosk/models/`` -
not a pip dependency, so nothing new to install, and it keeps working with no
network access once deployed. opencv-python-headless's own Haar cascade data files
are not present in this environment's build, which is why this uses YuNet instead.
"""

import cv2
import numpy as np
import frappe

MODEL_PATH = frappe.get_app_path(
    "cannabis_management", "manufacturing_timesheet_kiosk", "models", "face_detection_yunet_2023mar.onnx"
)

# Conservative but not paranoid: high enough to reject "no face at all" (a blank
# frame, a photo of a shoulder, a badge held up to the lens) without rejecting a
# real face at a slight angle or in mediocre kiosk lighting.
SCORE_THRESHOLD = 0.7

_detector = None


def _get_detector(width: int, height: int):
	"""A FaceDetectorYN sized for this image. Cheap to (re)create per call - the
	model load itself is what's expensive, and that part is cached process-wide."""
	global _detector
	if _detector is None:
		_detector = cv2.FaceDetectorYN_create(MODEL_PATH, "", (320, 320), score_threshold=SCORE_THRESHOLD)
	_detector.setInputSize((width, height))
	return _detector


def photo_has_face(content: bytes) -> bool:
	"""True if at least one face is detected in the given image bytes.

	Returns False (never raises) for anything the detector can't make sense of -
	an empty/corrupt image decodes to None, which is "no face" rather than a 500.
	"""
	try:
		arr = np.frombuffer(content, dtype=np.uint8)
		img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
		if img is None or img.size == 0:
			return False

		height, width = img.shape[:2]
		detector = _get_detector(width, height)
		_, faces = detector.detect(img)
		return faces is not None and len(faces) > 0
	except Exception:
		frappe.log_error(title="Kiosk face detection failed")
		return False
