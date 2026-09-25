"""Independent Type-1 WSPR-2 encoder.

The bit ordering and constants follow the official WSJT-X 3.0.2 sources:
``lib/wsprd/wsprsim_utils.c`` and ``lib/wsprd/fano.c``.  This module does
not invoke or import the official simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

CHANNEL_SYMBOL_COUNT = 162
POLY1 = 0xF2D05351
POLY2 = 0xE4613C47
VALID_POWERS_DBM = frozenset(
    (0, 3, 7, 10, 13, 17, 20, 23, 27, 30, 33, 37, 40, 43, 47, 50, 53, 57, 60)
)

# The fixed synchronization vector named pr3 in the matching implementation.
SYNC_BITS = (
    1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 0,
    0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1,
    0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 0, 1,
    1, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1,
    0, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0,
    0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1,
    0, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1,
    0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0,
    0, 0,
)


@dataclass(frozen=True)
class EncodingStages:
    """Observable stages of one Type-1 WSPR encoding operation."""

    message: str
    packed_callsign: int
    packed_grid_power: int
    information_bits: tuple[int, ...]
    terminated_bits: tuple[int, ...]
    packed_bytes: bytes
    convolutional_bits: tuple[int, ...]
    interleaved_bits: tuple[int, ...]
    channel_symbols: tuple[int, ...]


def _callsign_code(character: str) -> int:
    if character.isdigit():
        return ord(character) - ord("0")
    if "A" <= character <= "Z":
        return ord(character) - ord("A") + 10
    if character == " ":
        return 36
    raise ValueError(f"Unsupported callsign character: {character!r}")


def _pack_callsign(callsign: str) -> int:
    if not re.fullmatch(r"[A-Z0-9]{3,6}", callsign):
        raise ValueError("Callsign must contain 3 to 6 uppercase letters/digits")
    digit_positions = [index for index, char in enumerate(callsign) if char.isdigit()]
    if len(digit_positions) != 1 or digit_positions[0] not in (1, 2):
        raise ValueError("Type-1 callsign must have one digit in position 2 or 3")
    if not callsign[digit_positions[0] + 1 :].isalpha():
        raise ValueError("Characters after the callsign digit must be letters")

    call6 = callsign.ljust(6) if digit_positions[0] == 2 else (" " + callsign).ljust(6)
    if len(call6) != 6 or not call6[2].isdigit():
        raise ValueError("Callsign cannot be represented in the six-character Type-1 field")
    codes = [_callsign_code(char) for char in call6]
    if any(code < 10 or code > 36 for code in codes[3:]):
        raise ValueError("The final three callsign positions must be letters or spaces")

    packed = codes[0]
    packed = packed * 36 + codes[1]
    packed = packed * 10 + codes[2]
    packed = packed * 27 + codes[3] - 10
    packed = packed * 27 + codes[4] - 10
    packed = packed * 27 + codes[5] - 10
    return packed


def _pack_grid_power(grid: str, power_dbm: int) -> int:
    if not re.fullmatch(r"[A-R]{2}[0-9]{2}", grid):
        raise ValueError("Grid must be a four-character Maidenhead locator AA00 through RR99")
    if power_dbm not in VALID_POWERS_DBM:
        raise ValueError("Power must be a standard WSPR dBm value from 0 through 60")
    g0 = ord(grid[0]) - ord("A")
    g1 = ord(grid[1]) - ord("A")
    g2 = int(grid[2])
    g3 = int(grid[3])
    locator = (179 - 10 * g0 - g2) * 180 + 10 * g1 + g3
    return locator * 128 + power_dbm + 64


def _bits(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> shift) & 1 for shift in range(width - 1, -1, -1))


def _convolutional_encode(bits: tuple[int, ...]) -> tuple[int, ...]:
    state = 0
    output: list[int] = []
    for bit in bits:
        state = ((state << 1) | bit) & 0xFFFFFFFF
        output.append((state & POLY1).bit_count() & 1)
        output.append((state & POLY2).bit_count() & 1)
    return tuple(output)


def _reverse_byte(value: int) -> int:
    return int(f"{value:08b}"[::-1], 2)


def _interleave(bits: tuple[int, ...]) -> tuple[int, ...]:
    if len(bits) != CHANNEL_SYMBOL_COUNT:
        raise ValueError("WSPR interleaver requires exactly 162 coded bits")
    output = [0] * CHANNEL_SYMBOL_COUNT
    source_index = 0
    for index in range(256):
        destination = _reverse_byte(index)
        if destination < CHANNEL_SYMBOL_COUNT:
            output[destination] = bits[source_index]
            source_index += 1
            if source_index == CHANNEL_SYMBOL_COUNT:
                break
    return tuple(output)


def encode_type1(message: str) -> EncodingStages:
    """Encode an ordinary ``CALL GRID POWER`` message into 162 WSPR tones."""

    fields = message.strip().upper().split()
    if len(fields) != 3:
        raise ValueError("Type-1 message must have exactly CALL GRID POWER")
    callsign, grid, power_text = fields
    if not re.fullmatch(r"[0-9]+", power_text):
        raise ValueError("Power must be an integer in dBm")
    power_dbm = int(power_text)
    canonical = f"{callsign} {grid} {power_dbm}"

    packed_callsign = _pack_callsign(callsign)
    packed_grid_power = _pack_grid_power(grid, power_dbm)
    information = _bits(packed_callsign, 28) + _bits(packed_grid_power, 22)
    terminated = information + (0,) * 31

    # The official utility stores the 50 information bits plus zero tail in an
    # 11-byte, MSB-first buffer. The final seven padding bits are also zero.
    padded = terminated + (0,) * (88 - len(terminated))
    packed_bytes = bytes(
        sum(padded[offset + bit] << (7 - bit) for bit in range(8))
        for offset in range(0, 88, 8)
    )

    convolutional = _convolutional_encode(terminated)
    interleaved = _interleave(convolutional)
    symbols = tuple(2 * data_bit + sync_bit for data_bit, sync_bit in zip(interleaved, SYNC_BITS))
    return EncodingStages(
        message=canonical,
        packed_callsign=packed_callsign,
        packed_grid_power=packed_grid_power,
        information_bits=information,
        terminated_bits=terminated,
        packed_bytes=packed_bytes,
        convolutional_bits=convolutional,
        interleaved_bits=interleaved,
        channel_symbols=symbols,
    )
