# summarize a mitmproxy capture: python flows.py [filter] [-v]
import sys
from mitmproxy.io import FlowReader
flt = next((a for a in sys.argv[1:] if not a.startswith("-")), "")
verbose = "-v" in sys.argv
with open(__file__.replace("flows.py", "flows.mitm"), "rb") as f:
    for fl in FlowReader(f).stream():
        if not hasattr(fl, "request"): continue
        r = fl.request
        if flt not in r.pretty_url: continue
        code = fl.response.status_code if fl.response else "-"
        print(code, r.method, r.pretty_url[:160])
        if verbose:
            for k, v in r.headers.items(): print("   >", k, ":", v[:120])
            if r.content: print("   > body:", r.content[:600])
            if fl.response: print("   < body:", fl.response.content[:600])
