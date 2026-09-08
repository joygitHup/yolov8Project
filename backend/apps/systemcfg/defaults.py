import os

from apps.systemcfg.model_names import DEFAULT_MODEL_CLASS_NAMES

# Default local trained weights (override with env YOLO_WEIGHTS)
DEFAULT_YOLO_WEIGHTS = os.environ.get(
    "YOLO_WEIGHTS",
    r"D:\pythonDev\industrial_anomaly_detection\yolov8modle\runs\detect\train-6\weights\best.pt",
)

# Model class name -> system alert type
DEFAULT_LABEL_TYPE_MAP = {
    "火焰": "fire",
    "fire": "fire",
    "smoke": "fire",
    "乱停乱放": "parking",
    "网格区违停": "parking",
    "car": "parking",
    "truck": "parking",
    "bus": "parking",
    "bicycle": "parking",
    "motorcycle": "parking",
    "公交车": "parking",
    "自行车": "parking",
    "摩托车": "parking",
    "轿车": "parking",
    "卡车": "parking",
    "人员": "intrusion",
    "乱扔垃圾": "intrusion",
    "person": "intrusion",
    "烟雾": "fire",
    "烟雾小": "fire",
}


def default_settings():
    return {
        "detection": {
            "confidenceThreshold": 0.5,
            "iouThreshold": 0.45,
            "fps": 2,
            "maxDetections": 100,
            "categories": list(DEFAULT_MODEL_CLASS_NAMES),
            "trackingEnabled": True,
            "trackLostFrames": 30,
            "modelPath": DEFAULT_YOLO_WEIGHTS,
            "inferEnabled": True,
            "labelTypeMap": dict(DEFAULT_LABEL_TYPE_MAP),
        },
        "notification": {
            "enabled": True,
            "dingtalk": {"enabled": False, "webhook": "", "secret": "", "levels": ["high", "medium"], "types": ["intrusion", "fire"]},
            "email": {"enabled": False, "smtp": "", "port": 465, "from": "", "password": "", "recipients": "", "levels": ["high"], "types": ["fire", "intrusion"]},
            "sms": {"enabled": False, "provider": "aliyun", "accessKey": "", "secretKey": "", "sign": "", "templateId": "", "phones": "", "levels": ["high"]},
            "wework": {"enabled": False, "webhook": "", "levels": ["high", "medium"], "types": ["intrusion", "fire", "parking"]},
        },
        "alertDeduplication": {"enabled": True, "interval": 30},
        "flywheel": {
            "enabled": True,
            "alertFrames": True,
            "uncertainFrames": True,
            "uncertainLow": 0.25,
            "uncertainHigh": 0.55,
            "quotaPerCameraHour": 40,
            "sampleIntervalSec": 15,
            "autoLabelMin": 0.7,
            "autoApproveAlerts": False,
            "trainRoot": r"D:\pythonDev\industrial_anomaly_detection\yolov8modle",
            "epochs": 15,
            "batch": 4,
            "imgsz": 640,
            "minReviewed": 5,
            "maxMapDrop": 0.01,
            "trainDevice": "cpu",
        },
        "system": {"title": "YOLOv8 视频智能分析系统", "logo": "", "version": "1.0.0"},
    }
