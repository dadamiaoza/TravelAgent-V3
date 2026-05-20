"""天气查询工具。

优先使用和风天气 7d 预报 API（JWT Ed25519 认证）。
API 不可用时降级到 mock 兜底。
"""
import base64
import logging
import time
from datetime import datetime

import jwt
import requests
from cryptography.hazmat.primitives import serialization

from app.agents.tools.geo import geocode_poi
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── JWT Token 缓存 ──

_token_cache = {"token": "", "expires_at": 0}


def _get_jwt_token() -> str:
    """获取和风天气 JWT Token，缓存 1h，过期前 60s 自动刷新。"""
    now = time.time()
    if now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    # 加载 Ed25519 私钥（Base64 DER → cryptography 私钥对象）
    private_key_bytes = base64.b64decode(settings.qweather_private_key)
    private_key = serialization.load_der_private_key(private_key_bytes, password=None)

    # iat 设为当前时间前 30 秒，防止服务器时钟偏差导致"尚未生效"错误
    iat = int(now) - 30
    exp = iat + 3600

    token = jwt.encode(
        payload={"sub": settings.qweather_project_id, "iat": iat, "exp": exp},
        key=private_key,
        algorithm="EdDSA",
        headers={"kid": settings.qweather_key_id, "typ": None},  # 移除 typ 字段（和风建议不要）
    )

    _token_cache["token"] = token
    _token_cache["expires_at"] = exp
    return token


# ── 公共接口 ──

def get_weather(city: str, date: str) -> str:
    """查询城市在指定日期的天气。

    优先使用和风天气 7d 预报 API。API 不可用时降级到 mock。

    Args:
        city: 城市中文名，如 "北京"、"杭州"
        date: 日期 YYYY-MM-DD，如 "2026-06-01"

    Returns:
        天气摘要字符串（温度、天气状况、风力、出行建议）。
    """
    if settings.qweather_project_id and settings.qweather_api_host:
        try:
            result = _weather_qweather(city, date)
            if result:
                return result
        except Exception:
            logger.warning("和风天气查询失败，降级到 mock", exc_info=True)

    return _weather_mock(city, date)


# ── 和风天气 7d 预报 API ──

QWEATHER_7D_URL = "https://{host}/v7/weather/7d"


def _weather_qweather(city: str, date: str) -> str | None:
    """调用和风天气 7d 预报。返回格式化字符串，失败返回 None。"""
    # 第一步：地理编码获得坐标
    geo = geocode_poi(city)
    # 和风要求坐标最多 2 位小数
    location = f"{geo['lng']:.2f},{geo['lat']:.2f}"

    # 第二步：调用 7d 预报 API
    url = QWEATHER_7D_URL.format(host=settings.qweather_api_host)
    token = _get_jwt_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"location": location}

    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "200":
        return None

    # 第三步：在 7 天预报中找到目标日期
    daily_list = data.get("daily", [])
    if not daily_list:
        return None

    target = _find_day(daily_list, date)
    if target is None:
        return None

    # 第四步：格式化输出
    return _format_weather(city, date, target)


def _find_day(daily: list, date: str) -> dict | None:
    """在预报列表中查找匹配日期的条目。"""
    # 统一格式：API 可能返回 "2026-06-01" 或 "06-01"
    date_short = date[-5:]  # "MM-DD"
    for day in daily:
        fx = day.get("fxDate", "")
        if fx == date or fx.endswith(date_short):
            return day
    return None


def _format_weather(city: str, date: str, day: dict) -> str:
    """将和风天气单日数据格式化为摘要字符串。"""
    text_day = day.get("textDay", "未知")
    temp_max = day.get("tempMax", "?")
    temp_min = day.get("tempMin", "?")
    wind_dir = day.get("windDirDay", "未知")
    wind_scale = day.get("windScaleDay", "?")
    precip = day.get("precip", "0")

    # 出行建议
    advice = _travel_advice(text_day, temp_max, wind_scale, precip)

    return (
        f"{city} {date}：{text_day}，{temp_min}°C ~ {temp_max}°C，"
        f"{wind_dir}风 {wind_scale}级，{advice}"
    )


def _travel_advice(weather: str, temp_max: str, wind_scale: str, precip: str) -> str:
    """根据天气状况生成简短的出行建议。"""
    try:
        t = int(temp_max)
        w = int(wind_scale)
        p = float(precip)
    except (ValueError, TypeError):
        return "适合出行"

    parts = []
    if "雨" in weather:
        parts.append("建议带伞")
    if t > 35:
        parts.append("注意防暑")
    elif t < 5:
        parts.append("注意保暖")
    if w >= 6:
        parts.append("风力较大注意安全")

    return "，".join(parts) if parts else "适合出行"


# ── Mock 降级兜底 ──

def _weather_mock(city: str, date: str) -> str:
    """Mock 兜底：返回通用天气预报。"""
    return f"{city} {date}：晴转多云，15°C ~ 25°C，东北风 2-3 级，适合出行"
