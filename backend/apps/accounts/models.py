from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = (
        ("admin", "管理员"),
        ("operator", "操作员"),
        ("viewer", "查看者"),
    )
    name = models.CharField(max_length=64, blank=True, default="")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="viewer")
    phone = models.CharField(max_length=32, blank=True, default="")
    avatar = models.CharField(max_length=255, blank=True, default="")
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "users"
        ordering = ["id"]
