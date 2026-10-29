import cv2
import numpy as np
import frappe

MODEL_PATH = frappe.get_app_path(
    "cannabis_management", "manufacturing_timesheet_kiosk", "models", "face_detection_yunet_2023mar.onnx"
)

SCORE_THRESHOLD = 0.7

_detector = None


def _get_detector(width: int, height: int):
	global _detector
	if _detector is None:
		_detector = cv2.FaceDetectorYN_create(MODEL_PATH, "", (320, 320), score_threshold=SCORE_THRESHOLD)
	_detector.setInputSize((width, height))
	return _detector


def photo_has_face(content: bytes) -> bool:
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
