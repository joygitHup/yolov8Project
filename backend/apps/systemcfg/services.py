import copy
from apps.systemcfg.defaults import default_settings
from apps.systemcfg.models import SystemSetting


def get_all_settings():
    data = default_settings()
    for row in SystemSetting.objects.all():
        if isinstance(data.get(row.key), dict) and isinstance(row.value, dict):
            data[row.key] = deep_merge(data[row.key], row.value)
        elif row.key:
            data[row.key] = row.value
    return data


def get_section(key):
    defaults = default_settings().get(key, {})
    row = SystemSetting.objects.filter(key=key).first()
    if not row:
        return copy.deepcopy(defaults) if isinstance(defaults, dict) else defaults
    if isinstance(defaults, dict) and isinstance(row.value, dict):
        return deep_merge(defaults, row.value)
    return row.value


def save_section(key, value):
    SystemSetting.objects.update_or_create(key=key, defaults={"value": value})
    return value


def deep_merge(base, patch):
    result = copy.deepcopy(base)
    if not isinstance(patch, dict):
        return patch
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result
