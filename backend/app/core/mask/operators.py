"""单值脱敏算子：只做字符串变换，不涉及偏移与存储。"""

import re

from app.core.security import crypto

# 常见复姓：命中时保留两个字，避免“欧阳娜娜”被压成“欧某”
COMPOUND_SURNAMES = (
    "欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙", "慕容", "长孙",
    "宇文", "司徒", "司空", "令狐", "夏侯", "万俟", "闻人", "赫连", "澹台", "宗政",
    "濮阳", "淳于", "单于", "太叔", "申屠", "公羊", "轩辕", "钟离", "端木", "独孤",
    "南宫", "西门", "呼延", "第五", "鲜于", "百里", "东郭", "梁丘", "左丘", "微生",
)
_CHINESE_NAME = re.compile(r"^[\u4e00-\u9fa5]{2,}$")


def is_chinese_name(value: str) -> bool:
    """只把纯中文、两字以上的片段当作姓名，英文名等回退到占位符。"""
    return bool(_CHINESE_NAME.match(value))


def name_surname(value: str) -> str:
    for surname in COMPOUND_SURNAMES:
        if value.startswith(surname):
            return surname
    return value[:1]


def mask_value(value: str, keep_prefix: int = 0, keep_suffix: int = 0) -> str:
    if len(value) <= keep_prefix + keep_suffix:
        # 保留位已覆盖整串时退化为全遮蔽，避免原文被完整留下
        return "*" * len(value)
    head = value[:keep_prefix]
    # keep_suffix=0 时 value[-0:] 会取到整串，必须显式判空
    tail = value[len(value) - keep_suffix:] if keep_suffix else ""
    return head + "*" * (len(value) - keep_prefix - keep_suffix) + tail


def replace_value(value: str, token: str) -> str:
    return token


def fuzz_value(value: str, type_code: str) -> str:
    if type_code == "ADDRESS_CN":
        # 只保留省 / 市级前缀，非贪婪匹配避免吞掉后面更细的地址
        match = re.match(r"^(.{2,6}?(?:省|市|自治区))", value)
        # 没有行政区划特征时退化为前两字，至少保留可读的地域线索
        prefix = match.group(1) if match else value[:2]
        return f"{prefix}某处"
    if type_code == "NAME_CN":
        # 保留姓氏首字，其余打码；单字姓名也至少补一个星号
        return value[:1] + "*" * max(len(value) - 1, 1)
    return "[已模糊]"


def encrypt_value(value: str, key: bytes, aad: bytes) -> str:
    token = crypto.encrypt(key, value.encode("utf-8"), aad)
    # ENC: 前缀供逆序解密流程识别“这是可还原的令牌”而非普通占位符
    return "ENC:" + crypto.b64url_encode(token)
