import unittest
from parser_v2 import parse
E="K1ABC FN42 33"
def row(message):return "0000 -30  0.0  10.140200  0  "+message+" \n"
class ParserTests(unittest.TestCase):
 def p(self,s,status=0,stderr=""):return parse(s,status,E,stderr)
 def test_standard(self):self.assertEqual(self.p(row(E)+"<DecodeFinished>\n")["outcome"],"correct_decode")
 def test_seven_field(self):self.assertEqual(self.p(row("H87/YY8NKP 33")+"<DecodeFinished>\n")["decoded_messages"],["H87/YY8NKP 33"])
 def test_compound(self):self.assertEqual(self.p(row("097/K1IBC 7")+"<DecodeFinished>\n")["outcome"],"wrong_decode")
 def test_whitespace(self):self.assertEqual(self.p("  0000  -30  0.0 10.140200 0  K1ABC   FN42  33 \n<DecodeFinished>\n")["outcome"],"correct_decode")
 def test_multiple(self):self.assertEqual(len(self.p(row("H87/YY8NKP 33")+row("W9XYZ EN52 20")+"<DecodeFinished>\n")["decoded_messages"]),2)
 def test_expected_and_wrong(self):
  x=self.p(row(E)+row("H87/YY8NKP 33")+"<DecodeFinished>\n");self.assertTrue(x["expected_message_present"] and x["unexpected_message_present"])
 def test_no_decode(self):self.assertEqual(self.p("<DecodeFinished>\n")["outcome"],"no_decode")
 def test_info(self):self.assertEqual(self.p("Informational diagnostic line\n<DecodeFinished>\n")["outcome"],"no_decode")
 def test_malformed(self):self.assertEqual(self.p("0000 -30 BAD\n<DecodeFinished>\n")["outcome"],"ambiguous")
 def test_truncated(self):self.assertEqual(self.p(row(E))["outcome"],"ambiguous")
 def test_error(self):self.assertEqual(self.p("<DecodeFinished>\n",1)["outcome"],"ambiguous")
 def test_malloc(self):self.assertEqual(self.p("malloc failed\n<DecodeFinished>\n")["outcome"],"ambiguous")
 def test_hashed_call(self):self.assertEqual(self.p(row("<...> JO33 40")+"<DecodeFinished>\n")["decoded_messages"],["<...> JO33 40"])
if __name__=="__main__":unittest.main()
