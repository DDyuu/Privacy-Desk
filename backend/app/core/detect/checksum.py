"""证件与卡号的校验位算法（GB 11643 身份证、Luhn 银行卡）。"""

# 前 17 位的加权因子（ISO 7064 MOD 11-2）
GB11643_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
# 按加权和模 11 的余数 0..10 顺序取校验字符，X 代表 10
GB11643_CHECK = "10X98765432"


def gb11643_valid(value: str) -> bool:
    """18 位居民身份证号校验位验证。"""
    if len(value) != 18 or not value[:17].isdigit():
        return False
    total = sum(int(ch) * weight for ch, weight in zip(value[:17], GB11643_WEIGHTS))
    return GB11643_CHECK[total % 11] == value[17].upper()


def luhn_valid(value: str) -> bool:
    """银行卡 Luhn 校验。"""
    digits = [int(ch) for ch in value if ch.isdigit()]
    # 少于 12 位不可能构成有效卡号，提前剪枝减少误报
    if len(digits) < 12:
        return False
    total = 0
    # 从右往左，右起第 2、4、6… 位翻倍，超过 9 则减去 9（等价于各位相加）
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def validate_checksum(algo: str, value: str) -> bool:
    if algo == "gb11643":
        return gb11643_valid(value)
    if algo == "luhn":
        return luhn_valid(value)
    raise ValueError(f"未知校验算法：{algo}")
