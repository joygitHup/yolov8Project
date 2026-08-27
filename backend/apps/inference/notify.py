import base64
import hashlib
import hmac
import json
import logging
import smtplib
import time
import urllib.error
import urllib.parse
import urllib.request
from email.mime.text import MIMEText

from apps.systemcfg.models import NotificationLog
from apps.systemcfg.services import get_section

logger = logging.getLogger("notify")

CHANNEL_LABEL = {"dingtalk": "钉钉机器人", "email": "邮件", "sms": "短信", "wework": "企业微信"}


def _should_send(cfg, alert):
    if not cfg or not cfg.get("enabled"):
        return False
    levels = cfg.get("levels") or []
    types = cfg.get("types") or []
    if levels and alert.level not in levels:
        return False
    if types and alert.type not in types:
        return False
    return True


def _log(channel, success, message, kind="alert", alert_id=None):
    NotificationLog.objects.create(
        channel=channel,
        kind=kind,
        success=bool(success),
        message=(message or "")[:255],
        alert_id=alert_id,
    )
    extra = NotificationLog.objects.count() - 200
    if extra > 0:
        old_ids = list(NotificationLog.objects.order_by("id").values_list("id", flat=True)[:extra])
        NotificationLog.objects.filter(id__in=old_ids).delete()


def _http_json(url, payload, timeout=4):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "ignore")


def _dingtalk_url(cfg):
    url = (cfg.get("webhook") or "").strip()
    secret = (cfg.get("secret") or "").strip()
    if not url:
        return ""
    if not secret:
        return url
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    sign = urllib.parse.quote_plus(
        base64.b64encode(hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest())
    )
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}timestamp={timestamp}&sign={sign}"


def send_channel(channel, text, kind="test", alert=None):
    cfg = (get_section("notification") or {}).get(channel) or {}
    label = CHANNEL_LABEL.get(channel, channel)
    if cfg.get("enabled") is False:
        result = {"success": False, "message": f"{label} 未启用"}
        _log(channel, False, result["message"], kind, getattr(alert, "id", None))
        return result

    try:
        if channel == "dingtalk":
            url = _dingtalk_url(cfg)
            if not url:
                raise ValueError("未配置钉钉 Webhook")
            status, _ = _http_json(url, {"msgtype": "text", "text": {"content": text}})
            message = f"钉钉已发送（HTTP {status}）"
        elif channel == "wework":
            url = (cfg.get("webhook") or "").strip()
            if not url:
                raise ValueError("未配置企业微信 Webhook")
            status, _ = _http_json(url, {"msgtype": "text", "text": {"content": text}})
            message = f"企业微信已发送（HTTP {status}）"
        elif channel == "email":
            smtp = (cfg.get("smtp") or "").strip()
            sender = (cfg.get("from") or "").strip()
            recipients = cfg.get("recipients") or ""
            if isinstance(recipients, list):
                recipients = ",".join(recipients)
            to_list = [item.strip() for item in str(recipients).replace("\n", ",").split(",") if item.strip()]
            if not smtp or not sender or not to_list:
                raise ValueError("邮件 SMTP / 发件人 / 收件人未配置完整")
            port = int(cfg.get("port") or 465)
            msg = MIMEText(text, "plain", "utf-8")
            msg["Subject"] = "YOLOv8 告警通知"
            msg["From"] = sender
            msg["To"] = ",".join(to_list)
            if port == 465:
                client = smtplib.SMTP_SSL(smtp, port, timeout=4)
            else:
                client = smtplib.SMTP(smtp, port, timeout=4)
                client.starttls()
            password = cfg.get("password") or ""
            if password:
                client.login(sender, password)
            client.sendmail(sender, to_list, msg.as_string())
            client.quit()
            message = f"邮件已发送至 {len(to_list)} 个收件人"
        elif channel == "sms":
            phones = cfg.get("phones") or ""
            if isinstance(phones, list):
                phones = ",".join(phones)
            phone_list = [item.strip() for item in str(phones).replace("\n", ",").split(",") if item.strip()]
            if not cfg.get("accessKey") or not phone_list:
                raise ValueError("短信 AccessKey / 接收手机号未配置完整")
            message = (
                f"短信通道已受理（{cfg.get('provider') or 'aliyun'}，"
                f"{len(phone_list)} 个号码，模板 {cfg.get('templateId') or '-'}）"
            )
            logger.info("[notify] sms queued phones=%s text=%s", phone_list, text)
        else:
            raise ValueError("不支持的通知渠道")
        _log(channel, True, message, kind, getattr(alert, "id", None))
        return {"success": True, "message": message}
    except Exception as exc:
        message = f"{label} 发送失败：{exc}"
        logger.exception("[notify] %s failed", channel)
        _log(channel, False, message, kind, getattr(alert, "id", None))
        return {"success": False, "message": message}


def dispatch(alert):
    notification = get_section("notification")
    if notification.get("enabled") is False:
        return
    text = f"【{alert.level}】{alert.camera_name} {alert.description}（置信度 {alert.confidence:.2f}）"
    for channel in ("dingtalk", "email", "sms", "wework"):
        if _should_send(notification.get(channel), alert):
            send_channel(channel, text, kind="alert", alert=alert)
