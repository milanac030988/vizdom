"""
Build a single-file version of the EN deck with every figure inlined.

    python docs/present/build_standalone.py            # -> index-standalone.html
    python docs/present/build_standalone.py vi.html    # same for another deck

`index.html` stays the editable source (figures referenced by path, so they
can be regenerated from the .puml / sessions); the standalone file is what you
email, copy to a USB stick or open on a machine without the repo - no
`figures/` folder needed. Figures become base64 data URIs; the deck's own
lightbox works unchanged on them.
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def inline(src_name: str) -> Path:
    src = HERE / src_name
    html = src.read_text(encoding="utf-8")
    missing = []

    def to_data_uri(match):
        rel = match.group(1)
        path = HERE / rel
        if not path.is_file():
            missing.append(rel)
            return match.group(0)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f'src="data:{mime};base64,{data}"'

    out_html, n = re.subn(r'src="(figures/[^"]+)"', to_data_uri, html)
    out = src.with_name(src.stem + "-standalone" + src.suffix)
    out.write_text(out_html, encoding="utf-8")
    print(f"{src.name}: inlined {n - len(missing)} figure(s) -> {out.name} "
          f"({out.stat().st_size / 1024:.0f} KB)")
    for rel in missing:
        print(f"  !! missing figure, left as a path: {rel}")
    return out


if __name__ == "__main__":
    inline(sys.argv[1] if len(sys.argv) > 1 else "index.html")
