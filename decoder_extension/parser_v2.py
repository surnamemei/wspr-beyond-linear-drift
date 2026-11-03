"""Version 2 parser for WSJT-X 3.0.2 wsprd stdout."""
import re
VERSION="wsprd_stdout_v2.0"
NUMBER=r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
ROW=re.compile(r"^\s*(\d{4})\s+([+-]?\d+)\s+("+NUMBER+r")\s+("+NUMBER+r")\s+([+-]?\d+)\s+(.+?)\s*$")
PREFIX=re.compile(r"^\s*\d{4}(?:\s|$)")
CALL=re.compile(r"^[A-Za-z0-9<>./?+\-]+$")
POWER=re.compile(r"^[+-]?\d{1,2}$")
GRID=re.compile(r"^[A-Za-z0-9]+$")
def parse(stdout,exit_status,expected,stderr=""):
    messages=[]; bad=[]; done=0
    for line in stdout.splitlines():
        if line.strip()=="<DecodeFinished>":done+=1;continue
        m=ROW.fullmatch(line)
        if m:
            parts=m.group(6).split()
            if len(parts) in (2,3) and CALL.fullmatch(parts[0]) and POWER.fullmatch(parts[-1]) and (len(parts)==2 or GRID.fullmatch(parts[1])):
                messages.append(" ".join(parts))
            else:bad.append(line)
        elif PREFIX.match(line):bad.append(line)
    expected_present=expected in messages
    unexpected=any(x!=expected for x in messages)
    valid=exit_status==0 and done==1 and not bad and "malloc failed" not in stdout.lower() and not stderr.strip()
    return {"decoded_messages":messages,"expected_message_present":expected_present,
      "unexpected_message_present":unexpected,"outcome":("correct_decode" if expected_present else "wrong_decode" if messages else "no_decode") if valid else "ambiguous",
      "decoder_exit_status":exit_status,"parse_status":"ok" if valid else "invalid_or_incomplete",
      "parser_version":VERSION,"malformed_lines":bad,"finish_count":done}
