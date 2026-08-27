from rest_framework_simplejwt.tokens import AccessToken


def issue_token(user):
    token = AccessToken.for_user(user)
    token["role"] = user.role
    token["username"] = user.username
    return str(token)
