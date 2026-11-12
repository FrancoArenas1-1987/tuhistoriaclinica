import re


def normalize_rut(rut: str) -> str:
    cleaned = re.sub(r"[^0-9kK]", "", rut).upper()
    if len(cleaned) < 2:
        return rut
    return f"{cleaned[:-1]}-{cleaned[-1]}"


def validate_rut(rut: str) -> bool:
    cleaned = re.sub(r"[^0-9kK]", "", rut).upper()
    if len(cleaned) < 2:
        return False

    body = cleaned[:-1]
    verifier = cleaned[-1]
    if not body.isdigit():
        return False

    reverse_digits = map(int, reversed(body))
    factors = [2, 3, 4, 5, 6, 7]
    total = 0
    factor_index = 0
    for digit in reverse_digits:
        total += digit * factors[factor_index]
        factor_index = (factor_index + 1) % len(factors)

    remainder = 11 - (total % 11)
    expected = "0" if remainder == 11 else "K" if remainder == 10 else str(remainder)
    return verifier == expected

