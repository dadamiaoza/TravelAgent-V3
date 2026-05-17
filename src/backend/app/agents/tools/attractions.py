"""Attraction search and travel estimation tools — Step 4 of agent learning path."""

_MOCK_ATTRACTIONS: dict[str, list[dict]] = {
    "杭州": [
        {"name": "西湖", "category": "自然风光", "duration_h": 3, "rating": 4.9},
        {"name": "雷峰塔", "category": "历史古迹", "duration_h": 1.5, "rating": 4.6},
        {"name": "灵隐寺", "category": "寺庙", "duration_h": 2, "rating": 4.7},
        {"name": "龙井村", "category": "自然风光", "duration_h": 2.5, "rating": 4.5},
        {"name": "九溪烟树", "category": "自然风光", "duration_h": 2, "rating": 4.6},
        {"name": "苏堤", "category": "自然风光", "duration_h": 1.5, "rating": 4.8},
        {"name": "河坊街", "category": "美食购物", "duration_h": 2, "rating": 4.3},
        {"name": "宋城", "category": "主题公园", "duration_h": 4, "rating": 4.4},
        {"name": "西溪湿地", "category": "自然风光", "duration_h": 3, "rating": 4.5},
        {"name": "钱塘江大桥", "category": "城市地标", "duration_h": 1, "rating": 4.2},
    ],
    "北京": [
        {"name": "故宫", "category": "历史古迹", "duration_h": 4, "rating": 4.9},
        {"name": "天安门", "category": "城市地标", "duration_h": 1, "rating": 4.8},
        {"name": "天坛", "category": "历史古迹", "duration_h": 2, "rating": 4.7},
        {"name": "颐和园", "category": "自然风光", "duration_h": 3, "rating": 4.8},
        {"name": "长城", "category": "历史古迹", "duration_h": 5, "rating": 4.9},
        {"name": "鸟巢", "category": "现代建筑", "duration_h": 1.5, "rating": 4.3},
        {"name": "南锣鼓巷", "category": "美食购物", "duration_h": 2, "rating": 4.4},
        {"name": "798艺术区", "category": "文化艺术", "duration_h": 3, "rating": 4.5},
        {"name": "鼓楼", "category": "历史古迹", "duration_h": 1, "rating": 4.3},
        {"name": "簋街", "category": "美食购物", "duration_h": 2, "rating": 4.4},
    ],
    "上海": [
        {"name": "外滩", "category": "城市地标", "duration_h": 2, "rating": 4.8},
        {"name": "东方明珠", "category": "现代建筑", "duration_h": 2, "rating": 4.5},
        {"name": "南京路", "category": "美食购物", "duration_h": 2.5, "rating": 4.3},
        {"name": "豫园", "category": "历史古迹", "duration_h": 2, "rating": 4.4},
        {"name": "迪士尼", "category": "主题公园", "duration_h": 8, "rating": 4.7},
        {"name": "田子坊", "category": "美食购物", "duration_h": 2, "rating": 4.2},
        {"name": "上海博物馆", "category": "文化艺术", "duration_h": 2.5, "rating": 4.4},
        {"name": "新天地", "category": "美食购物", "duration_h": 1.5, "rating": 4.1},
        {"name": "朱家角", "category": "自然风光", "duration_h": 4, "rating": 4.3},
        {"name": "上海科技馆", "category": "现代建筑", "duration_h": 3, "rating": 4.2},
    ],
}

_TRAVEL_TIMES: dict[str, dict[str, int]] = {
    "西湖": {"雷峰塔": 20, "灵隐寺": 30, "龙井村": 35},
    "天安门": {"故宫": 10, "天坛": 25, "南锣鼓巷": 20},
    "外滩": {"南京路": 15, "豫园": 20, "东方明珠": 10},
}


def search_attractions(destination: str, preference: str = "") -> str:
    """Search for attractions in a destination city.

    Args:
        destination: City name in Chinese, e.g. "杭州", "北京"
        preference: Optional category filter, e.g. "自然风光", "历史古迹"

    Returns:
        Formatted string listing matching attractions with name, category, duration, rating.
    """
    if destination not in _MOCK_ATTRACTIONS:
        return f"未找到 {destination} 的景点数据。支持的城市：{', '.join(_MOCK_ATTRACTIONS.keys())}"

    pois = _MOCK_ATTRACTIONS[destination]
    if preference:
        pois = [p for p in pois if preference in p["category"]]
        if not pois:
            return f"{destination} 没有分类为「{preference}」的景点"

    lines = [f"{destination} 景点列表（偏好：{preference or '全部'}）："]
    for i, p in enumerate(pois, 1):
        lines.append(f"  {i}. {p['name']} | {p['category']} | 建议{p['duration_h']}h | 评分{p['rating']}")
    return "\n".join(lines)


def get_travel_time(from_poi: str, to_poi: str, mode: str = "walking") -> int:
    """Estimate travel time (minutes) between two POIs.

    Args:
        from_poi: Starting POI name in Chinese.
        to_poi: Destination POI name in Chinese.
        mode: Transport mode — "walking" (步行), "taxi" (打车), "transit" (公交).

    Returns:
        Estimated travel time in minutes.
    """
    # Check predefined pairs
    base = _TRAVEL_TIMES.get(from_poi, {}).get(to_poi)
    if base is None:
        base = _TRAVEL_TIMES.get(to_poi, {}).get(from_poi)
    if base is None:
        # Hash-based mock: different inputs give different but stable values
        import hashlib
        h = int(hashlib.md5(f"{from_poi}:{to_poi}".encode()).hexdigest()[:8], 16)
        base = 10 + (h % 40)  # 10-50 min default

    # Adjust by mode
    factors = {"walking": 1.0, "transit": 0.6, "taxi": 0.4}
    return max(5, int(base * factors.get(mode, 1.0)))
