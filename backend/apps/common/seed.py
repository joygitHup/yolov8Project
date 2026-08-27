from datetime import timedelta
from django.utils import timezone
from apps.accounts.models import User
from apps.cameras.models import Camera
from apps.alerts.models import Alert
from apps.systemcfg.models import Strategy, SystemSetting
from apps.systemcfg.defaults import default_settings


CAMERA_DEFS = [
    {"name": "东大门入口", "location": "园区东门", "ip": "192.168.1.101", "type": "hikvision", "status": "online", "resolution": "1920x1080"},
    {"name": "西大门入口", "location": "园区西门", "ip": "192.168.1.102", "type": "hikvision", "status": "online", "resolution": "1920x1080"},
    {"name": "地下车库A区", "location": "地库A-01", "ip": "192.168.1.103", "type": "dahua", "status": "online", "resolution": "1280x720"},
    {"name": "地下车库B区", "location": "地库B-01", "ip": "192.168.1.104", "type": "dahua", "status": "offline", "resolution": "1280x720"},
    {"name": "消防通道-1号楼", "location": "1号楼一层", "ip": "192.168.1.105", "type": "hikvision", "status": "online", "resolution": "1920x1080"},
    {"name": "围墙-北侧", "location": "北围墙中段", "ip": "192.168.1.106", "type": "hikvision", "status": "online", "resolution": "1920x1080"},
    {"name": "围墙-东侧", "location": "东围墙北段", "ip": "192.168.1.107", "type": "dahua", "status": "online", "resolution": "1280x720"},
    {"name": "中央广场", "location": "园区中心", "ip": "192.168.1.108", "type": "hikvision", "status": "online", "resolution": "1920x1080"},
]

DESCRIPTIONS = {
    "intrusion": ["检测到人员进入警戒区域", "检测到车辆越界", "围墙区域发现可疑人员", "禁区内检测到移动物体"],
    "parking": ["消防通道发现违停车辆", "通道处检测到电动车停放", "禁停区域有物品堆放", "应急通道被占用"],
    "fire": ["检测到明火", "发现烟雾", "疑似火灾隐患", "烟雾浓度异常"],
}


def _boxes(alert_type):
    import random
    count = random.randint(1, 3)
    boxes = []
    for _ in range(count):
        label = "person"
        if alert_type == "parking":
            label = random.choice(["car", "truck"])
        if alert_type == "fire":
            label = random.choice(["fire", "smoke"])
        boxes.append({
            "x": round(random.random() * 0.6 + 0.1, 4),
            "y": round(random.random() * 0.5 + 0.2, 4),
            "w": round(random.random() * 0.2 + 0.1, 4),
            "h": round(random.random() * 0.3 + 0.15, 4),
            "label": label,
            "confidence": round(0.7 + random.random() * 0.28, 2),
        })
    return boxes


def seed_if_empty():
    if User.objects.exists():
        print("[seed] 已有数据，跳过")
        return
    print("[seed] 写入演示数据...")
    User.objects.create_user(username="admin", password="admin123", name="系统管理员", role="admin", email="admin@example.com", phone="13800138000")
    User.objects.create_user(username="operator", password="operator123", name="值班操作员", role="operator", email="operator@example.com", phone="13900139000")
    User.objects.create_user(username="viewer", password="viewer123", name="查看员", role="viewer", email="viewer@example.com", phone="13700137000")

    cameras = []
    for idx, item in enumerate(CAMERA_DEFS):
        cameras.append(Camera.objects.create(
            name=item["name"],
            location=item["location"],
            ip=item["ip"],
            rtsp=f"rtsp://{item['ip']}/stream",
            type=item["type"],
            username="admin",
            password="admin123",
            resolution=item["resolution"],
            status=item["status"],
            enabled=True,
            detection_types=["intrusion", "parking", "fire"],
        ))

    import random
    types = ["intrusion", "parking", "fire"]
    now = timezone.now()
    for i in range(50):
        alert_type = random.choice(types)
        camera = random.choice(cameras)
        status = "unhandled" if i < 15 else ("processing" if i < 30 else "resolved")
        level = "high" if alert_type == "fire" else ("medium" if alert_type == "intrusion" else "low")
        triggered = now - timedelta(hours=i * (random.random() * 2 + 0.5))
        Alert.objects.create(
            camera=camera,
            camera_name=camera.name,
            type=alert_type,
            level=level,
            description=random.choice(DESCRIPTIONS[alert_type]),
            status=status,
            confidence=round(0.75 + random.random() * 0.24, 2),
            snapshot_url=f"/mock/alert-{i % 8}.jpg",
            image_url=f"/mock/alert-{i % 8}.jpg",
            video_url=f"/mock/alert-{i % 8}.mp4",
            detection_boxes=_boxes(alert_type),
            triggered_at=triggered,
            resolved_at=triggered + timedelta(minutes=30) if status == "resolved" else None,
            resolved_by="admin" if status == "resolved" else "",
            resolved_note="已确认并处置完毕" if status == "resolved" else "",
        )

    settings = default_settings()
    for key, value in settings.items():
        SystemSetting.objects.update_or_create(key=key, defaults={"value": value})

    Strategy.objects.create(
        name="全天入侵检测",
        camera_ids=[cameras[0].id, cameras[1].id, cameras[5].id, cameras[6].id],
        detection_types=["intrusion"],
        schedule={"type": "always"},
        alert_level="medium",
        enabled=True,
    )
    Strategy.objects.create(
        name="工作时间消防通道检测",
        camera_ids=[cameras[4].id],
        detection_types=["parking", "fire"],
        schedule={"type": "worktime", "start": "08:00", "end": "20:00"},
        alert_level="high",
        enabled=True,
    )
    Strategy.objects.create(
        name="夜间围墙重点布防",
        camera_ids=[cameras[5].id, cameras[6].id],
        detection_types=["intrusion", "fire"],
        schedule={"type": "night", "start": "22:00", "end": "06:00"},
        alert_level="high",
        enabled=True,
    )
    print("[seed] 完成：3 用户 / 8 摄像头 / 50 告警 / 3 策略")
