def default_settings():
    return {
        "detection": {
            "confidenceThreshold": 0.5,
            "iouThreshold": 0.45,
            "fps": 2,
            "maxDetections": 100,
            "categories": ["person", "car", "truck", "fire", "smoke"],
            "trackingEnabled": True,
            "trackLostFrames": 30,
        },
        "notification": {
            "enabled": True,
            "dingtalk": {"enabled": False, "webhook": "", "secret": "", "levels": ["high", "medium"], "types": ["intrusion", "fire"]},
            "email": {"enabled": False, "smtp": "", "port": 465, "from": "", "password": "", "recipients": "", "levels": ["high"], "types": ["fire", "intrusion"]},
            "sms": {"enabled": False, "provider": "aliyun", "accessKey": "", "secretKey": "", "sign": "", "templateId": "", "phones": "", "levels": ["high"]},
            "wework": {"enabled": False, "webhook": "", "levels": ["high", "medium"], "types": ["intrusion", "fire", "parking"]},
        },
        "alertDeduplication": {"enabled": True, "interval": 30},
        "system": {"title": "YOLOv8 视频智能分析系统", "logo": "", "version": "1.0.0"},
    }
