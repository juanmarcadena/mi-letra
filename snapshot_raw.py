"""Copy the handwriting source out of Notability: for every note, only the pen strokes
(Session.plist) and the recognised text (HandwritingIndex). Read-only on the notes.
   python snapshot_raw.py  -> data/raw/<note>/...   (extract.py reads from here if LETRA_RAW=1)"""
import glob, os, shutil
SRC = os.path.expanduser("~/Library/Mobile Documents/ZP9ZJ4EF3S~com~gingerlabs~Notability/Documents")
n = size = 0
for nbn in sorted(glob.glob(SRC + "/*.nbn")):
    dst = os.path.join("data", "raw", os.path.basename(nbn))
    for rel in ("Session.plist", os.path.join("HandwritingIndex", "index.plist")):
        s = os.path.join(nbn, rel)
        if os.path.exists(s):
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copy2(s, os.path.join(dst, rel))
            size += os.path.getsize(s)
    n += 1
print(f"notes copied: {n} | {size / 1e6:.0f} MB in data/raw")
