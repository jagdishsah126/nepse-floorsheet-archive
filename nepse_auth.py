"""
NEPSE Authentication and Dynamic Payload ID Generator.

Reverse-engineered from NEPSE's frontend Angular app & WebAssembly bytecode.
Calculates valid 'Salter <token>' header and the dynamic POST body '{"id": <calculated_id>}'.
"""

from datetime import datetime
from typing import Any, Dict, List, Tuple
import pytz

# Lookup table extracted from NEPSE's css.wasm module
LOOKUP_TABLE: List[int] = [
    5, 8, 4, 7, 9, 4, 6, 9, 5, 5,
    6, 5, 3, 5, 4, 4, 9, 6, 6, 8,
    8, 6, 8, 6, 5, 8, 4, 9, 5, 9,
    8, 5, 3, 4, 7, 7, 4, 7, 3, 9
]

# Dummy data array from NEPSE's Angular client bundle
DUMMY_DATA: List[int] = [
    147, 117, 239, 143, 157, 312, 161, 612, 512, 804, 411, 527, 170, 511, 421, 667, 764, 621,
    301, 106, 133, 793, 411, 511, 312, 423, 344, 346, 653, 758, 342, 222, 236, 811, 711, 611,
    122, 447, 128, 199, 183, 135, 489, 703, 800, 745, 152, 863, 134, 211, 142, 564, 375, 793,
    212, 153, 138, 153, 648, 611, 151, 649, 318, 143, 117, 756, 119, 141, 717, 113, 112, 146,
    162, 660, 693, 261, 362, 354, 251, 641, 157, 178, 631, 192, 734, 445, 192, 883, 187, 122,
    591, 731, 852, 384, 565, 596, 451, 772, 624, 691
]


def cdx(v: int) -> int:
    ones = v % 10
    tens = (v // 10) % 10
    hundreds = (v // 100) % 10
    return LOOKUP_TABLE[ones + tens + hundreds] + 22


def rdx(v: int) -> int:
    ones = v % 10
    tens = (v // 10) % 10
    hundreds = (v // 100) % 10
    v_sum = tens + hundreds
    return v_sum + LOOKUP_TABLE[v_sum + ones] + 32


def bdx(v: int) -> int:
    ones = v % 10
    tens = (v // 10) % 10
    hundreds = (v // 100) % 10
    v_sum = tens + hundreds
    return v_sum + LOOKUP_TABLE[v_sum + ones] + 60


def ndx(v: int) -> int:
    ones = v % 10
    tens = (v // 10) % 10
    hundreds = (v // 100) % 10
    return tens + LOOKUP_TABLE[tens + ones + hundreds] + 88


def mdx(v: int) -> int:
    ones = v % 10
    tens = (v // 10) % 10
    hundreds = (v // 100) % 10
    return hundreds + LOOKUP_TABLE[hundreds + tens + ones] + 110


def parse_access_token(prove_response: Dict[str, Any]) -> str:
    """
    De-obfuscate NEPSE access token using salt values.
    Removes slices at indices determined by cdx, rdx, bdx, ndx, mdx.
    """
    token: str = prove_response["accessToken"]
    salt2: int = int(prove_response["salt2"])

    n = cdx(salt2)
    l = rdx(salt2)
    o = bdx(salt2)
    p = ndx(salt2)
    q = mdx(salt2)

    return (
        token[:n]
        + token[n + 1 : l]
        + token[l + 1 : o]
        + token[o + 1 : p]
        + token[p + 1 : q]
        + token[q + 1 :]
    )


def calculate_floorsheet_payload_id(market_open_id: int, prove_response: Dict[str, Any]) -> int:
    """
    Calculate the dynamic payload ID required in the POST body {"id": ...} for floorsheet requests.

    Formula from NEPSE frontend:
      var i = dummyData[dummyId] + dummyId + 2 * day;
      payloadId = i + accessTokens[i % 10 < 4 ? 1 : 3] * day - accessTokens[(i % 10 < 4 ? 1 : 3) - 1];
    """
    # Use Nepal timezone for day calculation
    tz = pytz.timezone("Asia/Kathmandu")
    day = datetime.now(tz).day

    access_tokens = [
        int(prove_response["salt1"]),
        int(prove_response["salt2"]),
        int(prove_response["salt3"]),
        int(prove_response["salt4"]),
        int(prove_response["salt5"]),
    ]

    dummy_val = DUMMY_DATA[market_open_id] if market_open_id < len(DUMMY_DATA) else DUMMY_DATA[0]
    i = dummy_val + market_open_id + 2 * day
    idx = 1 if (i % 10 < 4) else 3
    payload_id = i + access_tokens[idx] * day - access_tokens[idx - 1]

    return payload_id
