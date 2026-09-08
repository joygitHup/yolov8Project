from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed, NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from apps.common.apiview import APIView
from apps.common.pagination import paginate_qs
from apps.common.permissions import IsAdminRole
from apps.common.tokens import issue_token
from .authentication import bearer_token, clear_access_cookie, set_access_cookie
from .models import User
from .serializers import LoginSerializer, PasswordSerializer, UserSerializer


def _checked_password(raw, user=None) -> str:
    text = str(raw or "")
    if not text.strip():
        raise ValidationError("密码不能为空")
    try:
        validate_password(text, user=user)
    except DjangoValidationError as exc:
        raise ValidationError(list(exc.messages)) from exc
    return text


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        username = ser.validated_data["username"]
        password = ser.validated_data["password"]
        user = authenticate(request, username=username, password=password)
        if user is None:
            exists = User.objects.filter(username=username).first()
            if exists and not exists.is_active:
                raise AuthenticationFailed("账户已被禁用")
            raise AuthenticationFailed("用户名或密码错误")
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        token = issue_token(user)
        response = Response({"user": UserSerializer(user).data})
        set_access_cookie(response, token, request)
        return response


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({"message": "登出成功"})
        clear_access_cookie(response)
        return response


class MeView(APIView):
    def get(self, request):
        response = Response(UserSerializer(request.user).data)
        raw = bearer_token(request)
        if raw:
            set_access_cookie(response, raw, request)
        return response


class ChangePasswordView(APIView):
    def post(self, request):
        ser = PasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if not request.user.check_password(ser.validated_data["oldPassword"]):
            raise ValidationError("原密码错误")
        new_password = _checked_password(ser.validated_data["newPassword"], user=request.user)
        request.user.set_password(new_password)
        request.user.save()
        return Response({"message": "密码修改成功"})


class UserListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        qs = User.objects.all()
        keyword = request.query_params.get("keyword") or ""
        role = request.query_params.get("role") or ""
        if keyword:
            qs = qs.filter(Q(username__icontains=keyword) | Q(name__icontains=keyword))
        if role:
            qs = qs.filter(role=role)
        return Response(paginate_qs(qs.order_by("id"), request, UserSerializer))

    def post(self, request):
        username = request.data.get("username")
        if not username:
            raise ValidationError("用户名不能为空")
        if User.objects.filter(username=username).exists():
            raise ValidationError("用户名已存在")
        password = _checked_password(request.data.get("password"))
        enabled = request.data.get("enabled", True)
        user = User.objects.create_user(
            username=username,
            password=password,
            name=request.data.get("realName") or request.data.get("name") or username,
            role=request.data.get("role") or "viewer",
            email=request.data.get("email") or "",
            phone=request.data.get("phone") or "",
            is_active=bool(enabled),
        )
        return Response(UserSerializer(user).data)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def _get(self, pk):
        user = User.objects.filter(pk=pk).first()
        if not user:
            raise NotFound("用户不存在")
        return user

    def put(self, request, pk):
        user = self._get(pk)
        if "realName" in request.data or "name" in request.data:
            user.name = request.data.get("realName") or request.data.get("name") or user.name
        if "role" in request.data and request.data["role"]:
            user.role = request.data["role"]
        if "email" in request.data:
            user.email = request.data.get("email") or ""
        if "phone" in request.data:
            user.phone = request.data.get("phone") or ""
        if "enabled" in request.data:
            user.is_active = bool(request.data.get("enabled"))
        if request.data.get("status") == "disabled":
            user.is_active = False
        if request.data.get("status") == "active":
            user.is_active = True
        user.save()
        return Response(UserSerializer(user).data)

    def delete(self, request, pk):
        user = self._get(pk)
        if user.id == request.user.id:
            raise ValidationError("不能删除自己")
        user.delete()
        return Response({"message": "删除成功"})


class UserToggleStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if not user:
            raise NotFound("用户不存在")
        if user.id == request.user.id:
            raise ValidationError("不能禁用自己")
        if "enabled" in request.data:
            user.is_active = bool(request.data.get("enabled"))
        else:
            user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        return Response({"enabled": user.is_active, "user": UserSerializer(user).data})


class ResetPasswordView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if not user:
            raise NotFound("用户不存在")
        password = _checked_password(request.data.get("newPassword"), user=user)
        user.set_password(password)
        user.save()
        return Response({"message": "密码重置成功"})
