import json
from pathlib import Path
import unittest

from wspr.encoder import encode_type1


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / "tests/data/reference_symbols.json").read_text())


class Type1EncoderTests(unittest.TestCase):
    def test_official_reference_matches_all_162_symbols(self):
        encoded = encode_type1(REFERENCE["message"])
        expected = REFERENCE["channel_symbols"]
        mismatches = [
            (index, expected_symbol, actual_symbol)
            for index, (expected_symbol, actual_symbol) in enumerate(
                zip(expected, encoded.channel_symbols)
            )
            if expected_symbol != actual_symbol
        ]
        self.assertEqual(
            len(encoded.channel_symbols),
            len(expected),
            "Python and official symbol vectors have different lengths",
        )
        self.assertEqual(mismatches, [], f"Mismatching symbol indices: {mismatches}")

    def test_official_packed_message_and_stage_lengths(self):
        encoded = encode_type1("K1ABC FN42 33")
        self.assertEqual(
            encoded.packed_bytes.hex(" ").upper(),
            " ".join(REFERENCE["packed_data_11_bytes_hex"]),
        )
        self.assertEqual(len(encoded.information_bits), 50)
        self.assertEqual(len(encoded.terminated_bits), 81)
        self.assertEqual(encoded.terminated_bits[-31:], (0,) * 31)
        self.assertEqual(len(encoded.convolutional_bits), 162)
        self.assertEqual(len(encoded.interleaved_bits), 162)

    def test_type1_output_domain_and_canonicalization(self):
        encoded = encode_type1("k1abc fn42 33")
        self.assertEqual(encoded.message, "K1ABC FN42 33")
        self.assertEqual(len(encoded.channel_symbols), 162)
        self.assertLessEqual(set(encoded.channel_symbols), {0, 1, 2, 3})

    def test_invalid_type1_messages_are_rejected(self):
        for message in ("K1ABC", "K1ABC ZZ99 33", "ABCDEF FN42 33", "K1ABC FN42 34"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                encode_type1(message)


if __name__ == "__main__":
    unittest.main()
