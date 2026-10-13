"""Second opinion on every extracted word: render it and read it with Apple's
on-device text recognition (Vision). Words where Vision agrees with
Notability's label are marked verified. Nothing leaves the Mac.
Writes data/ocr.pkl: {word_idx: (text, confidence)}.
"""
import os, pickle, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw
import Vision
from Foundation import NSURL

ROWS, RH, WIDTH, XH = 36, 96, 900, 20


def read(path):
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    req.setRecognitionLanguages_(["en-US", "es-ES"])
    h = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(path), None)
    ok, err = h.performRequests_error_([req], None)
    out = []
    for o in (req.results() or []):
        c = o.topCandidates_(1)
        if c:
            bb = o.boundingBox()
            out.append((bb.origin.x, 1 - (bb.origin.y + bb.size.height / 2), str(c[0].string()), float(c[0].confidence())))
    return out


def main():
    B = pickle.load(open("data/bank.pkl", "rb"))
    words = B["words"]
    todo = [i for i, w in enumerate(words) if len(w["label"]) >= 2 and w["w"] * XH < WIDTH - 60]
    res, tmp = {}, tempfile.mkdtemp()
    for b0 in range(0, len(todo), ROWS):
        batch = todo[b0:b0 + ROWS]
        img = Image.new("L", (WIDTH, ROWS * RH), 255)
        d = ImageDraw.Draw(img)
        for r, wi in enumerate(batch):
            w = words[wi]
            by = r * RH + 62
            for s in w["strokes"]:
                pts = [(30 + x * XH, by - y * XH) for x, y in s]
                if len(pts) == 1:
                    d.ellipse([pts[0][0] - 2, pts[0][1] - 2, pts[0][0] + 2, pts[0][1] + 2], fill=0)
                else:
                    d.line(pts, fill=0, width=3, joint="curve")
        p = os.path.join(tmp, "b.png")
        img.save(p)
        rows = {}
        for x, yc, t, cf in read(p):
            rows.setdefault(int(yc * ROWS), []).append((x, t, cf))
        for r, wi in enumerate(batch):
            items = sorted(rows.get(r, []))
            res[wi] = ("".join(t for _, t, _ in items), min([c for *_, c in items], default=0.0))
        if (b0 // ROWS) % 40 == 0:
            print(b0, "/", len(todo), flush=True)
    pickle.dump(res, open("data/ocr.pkl", "wb"))
    norm = lambda s: "".join(s.split()).casefold()
    agree = sum(norm(t) == norm(words[i]["label"]) for i, (t, c) in res.items())
    print(f"words read {len(res)} | Vision agrees with Notability on {agree} ({100 * agree / max(1, len(res)):.0f}%)")
    ex = [(words[i]["label"], t) for i, (t, c) in list(res.items())[:400] if norm(t) != norm(words[i]["label"])][:14]
    print("disagreements e.g.:", ex)


if __name__ == "__main__":
    main()
