"""Fill PDF forms in Juan's handwriting, addressing fields by their printed label.

    from forma import Form
    f = Form("blank.pdf")
    f.line("Nombre", "Juan Martín Cadena")
    f.check("Duplicidad de cargos")
    f.cell("Fecha Transacción", 1, "04/10/2026 23:48")       # table column header, data row
    f.box("COMENTARIOS ADICIONALES", "texto largo…")          # the big rectangle under that label
    f.at(page, x0, y0, x1, y1, "texto")                       # anything the finder misses
    f.save("filled.pdf")

Text shrinks to fit a line or cell, and wraps then shrinks to fit a box.
`python forma.py blank.pdf` lists the fields it can find.
Never used for card numbers, passwords or signatures: those are Juan's to write.
"""
import random, sys, unicodedata
import pymupdf
import avgfont as F

INK = (0.05, 0.1, 0.45)


def _norm(s):
    s = unicodedata.normalize("NFD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c) and (c.isalnum() or c == " ")).strip()


def text_width(text, t=0.35):
    """Width of one line in x-heights (average over the variants a letter may get)."""
    return max(F.layout(text, t, seed=s)[1] for s in (0, 1, 2))


class Form:
    def __init__(self, path, xh=4.5, min_xh=2.9, color=INK, pen=0.14, seed=7, style="molde"):
        F.use_style(style)       # "molde" (separate letters, the default for forms) or "cursiva"
        self.doc = pymupdf.open(path)
        self.xh, self.min_xh, self.color, self.pen = xh, min_xh, color, pen
        self.rng = random.Random(seed)
        self.log = []
        self._scan()

    # ---------- finding fields ----------
    def _scan(self):
        self.spans, self.hlines, self.vlines, self.rects, self.boxes = [], [], [], [], []
        for pno, page in enumerate(self.doc):
            for b in page.get_text("rawdict")["blocks"]:
                for ln in b.get("lines", []):
                    for sp in ln["spans"]:
                        txt = "".join(c["c"] for c in sp["chars"])
                        if txt.strip():
                            self.spans.append(dict(page=pno, text=txt, bbox=pymupdf.Rect(sp["bbox"]), chars=sp["chars"], base=sp["origin"][1]))
                        for c in sp["chars"]:
                            if c["c"] in "☐□▢❏":
                                self.boxes.append(dict(page=pno, rect=pymupdf.Rect(c["bbox"]), base=c["origin"][1]))
            for d in page.get_drawings():
                r = d["rect"]
                if r.width >= 25 and r.height <= 2.5:
                    self.hlines.append((pno, r.x0, r.x1, (r.y0 + r.y1) / 2))
                elif r.height >= 8 and r.width <= 2.5:
                    self.vlines.append((pno, (r.x0 + r.x1) / 2, r.y0, r.y1))
                elif r.width >= 150 and r.height >= 50:
                    self.rects.append((pno, pymupdf.Rect(r)))
            for w in page.widgets() or []:      # real form fields, when the PDF has them
                self.rects.append((pno, pymupdf.Rect(w.rect)))

    def _label(self, label, nth=0):
        key = _norm(label)
        hits = [s for s in self.spans if key in _norm(s["text"])]
        if len(hits) <= nth:
            raise KeyError(f"label not found on the form: {label!r}")
        s = hits[nth]
        # tight box of just the matching words, so a long span does not hide the field next to it
        low = _norm(s["text"])
        return s

    def _underline(self, label, nth=0):
        s = self._label(label, nth)
        cands = [(x0, x1, y) for p, x0, x1, y in self.hlines
                 if p == s["page"] and -4 <= y - s["base"] <= 6 and x1 > s["bbox"].x0 + 20]
        if not cands:
            raise KeyError(f"no writing line found next to {label!r}")
        # the line that starts closest to the end of the label's own words
        end = self._label_end(s, label)
        x0, x1, y = min(cands, key=lambda c: abs(c[0] - end))
        return s["page"], max(x0, end + 2) if x0 < end else x0, x1, y

    def _label_end(self, s, label):
        key = _norm(label)
        acc = ""
        for c in s["chars"]:
            acc += c["c"]
            if key in _norm(acc):
                return c["bbox"][2]
        return s["bbox"].x1

    def fields(self):
        """Human-readable list of what the finder sees."""
        out = []
        seen = set()
        for p, x0, x1, y in self.hlines:      # each writing line once, named after the text just before it
            key = (p, round(x0), round(x1), round(y))      # some PDFs draw the same line twice
            if key in seen:
                continue
            seen.add(key)
            near = [s for s in self.spans if p == s["page"] and -4 <= y - s["base"] <= 6
                    and x0 >= s["bbox"].x0 and x0 - s["bbox"].x1 < 40]
            if near and x1 - x0 < 400:
                s = min(near, key=lambda s: abs(x0 - s["bbox"].x1))
                out.append(f"p{p + 1} line   after {s['text'].strip()[:45]!r}  ({x1 - x0:.0f} pt wide)")
        for b in self.boxes:
            lab = self._box_label(b)
            out.append(f"p{b['page'] + 1} check  {lab[:50]!r}")
        for p, r in self.rects:
            out.append(f"p{p + 1} box    {r.width:.0f} x {r.height:.0f} pt at y={r.y0:.0f}")
        for p, cols, rows in self._tables():
            heads = [self._cell_text(p, cols[i], cols[i + 1], rows[0], rows[1]) for i in range(len(cols) - 1)]
            out.append(f"p{p + 1} table  {len(rows) - 2} data rows, columns {heads}")
        return out

    def _box_label(self, b):
        best = ""
        for s in self.spans:
            if s["page"] == b["page"] and abs(s["base"] - b["base"]) < 3:
                after = "".join(c["c"] for c in s["chars"] if c["bbox"][0] >= b["rect"].x1 - 1)
                after = after.split("☐")[0].strip()
                if after:
                    best = after
        return best

    def _tables(self):
        out = []
        for p in range(len(self.doc)):
            ys = sorted({round(y, 0) for q, x0, x1, y in self.hlines if q == p and x1 - x0 > 60})
            xs = sorted({round(x, 0) for q, x, y0, y1 in self.vlines if q == p})
            # merge near-duplicates
            mg = lambda v: [a for i, a in enumerate(v) if i == 0 or a - v[i - 1] > 3]
            xs, ys = mg(xs), mg(ys)
            rows = [y for y in ys if any(q == p and y0 - 2 <= y <= y1 + 2 for q, x, y0, y1 in self.vlines)]
            if len(xs) >= 3 and len(rows) >= 3:
                out.append((p, xs, rows))
        return out

    def _cell_text(self, p, x0, x1, y0, y1):
        r = pymupdf.Rect(x0, y0, x1, y1)
        return " ".join(s["text"].strip() for s in self.spans if s["page"] == p and r.contains(s["bbox"].tl + (2, 2)))

    # ---------- writing ----------
    def _fit(self, text, width_pt, xh=None):
        xh = xh or self.xh
        w = text_width(text)
        if w * xh > width_pt:
            xh = max(self.min_xh, width_pt / w)
        return xh

    def _write(self, pno, text, x, baseline, xh):
        F.write_line(self.doc[pno], text, x, baseline, xh_pt=xh, color=self.color, pen=self.pen,
                     seed=self.rng.randrange(10 ** 6))

    def at(self, pno, x0, y0, x1, y1, text, xh=None):
        """One line inside the rectangle, sitting near its bottom."""
        xh = self._fit(text, x1 - x0 - 2, xh)
        self._write(pno, text, x0 + 1, y1 - 0.35 * xh - 1.5, xh)
        self.log.append((text, round(xh, 2)))
        return self

    def line(self, label, text, nth=0, xh=None):
        """Write on the underline that follows a printed label."""
        p, x0, x1, y = self._underline(label, nth)
        xh = self._fit(text, x1 - x0 - 4, xh)
        self._write(p, text, x0 + 2.5, y - 0.3 * xh - 0.6, xh)
        self.log.append((label, round(xh, 2)))
        return self

    def lines(self, label, parts):
        """Several short underlines after one label, left to right (e.g. day / month / year)."""
        s = self._label(label)
        row = sorted((x0, x1, y) for p, x0, x1, y in self.hlines if p == s["page"] and -4 <= y - s["base"] <= 6 and x0 > s["bbox"].x0)
        for (x0, x1, y), txt in zip(row, parts):
            xh = self._fit(txt, x1 - x0 - 2)
            w = text_width(txt) * xh
            self._write(s["page"], txt, x0 + max(1, (x1 - x0 - w) / 2), y - 0.3 * xh - 0.6, xh)
        return self

    def check(self, label, mark="X"):
        """Mark the checkbox printed next to a label, with Juan's own X or check mark."""
        key = _norm(label)
        hit = [b for b in self.boxes if key in _norm(self._box_label(b))]
        if not hit:
            raise KeyError(f"no checkbox found for {label!r}")
        b = hit[0]
        g = F.glyph("✗" if mark == "X" else "✓", 0.35, self.rng.randrange(3)) or F.glyph("X", 0.35, 0)
        x0, y0, x1, y1 = F.bbox(g)
        r = b["rect"]
        side = min(r.width, r.height)
        k = 1.25 * side / max(x1 - x0, y1 - y0)          # a little bigger than the box, like a real tick
        cx, cy = (r.x0 + r.x1) / 2 + self.rng.gauss(0, 0.4), (r.y0 + r.y1) / 2 + self.rng.gauss(0, 0.4) + 0.12 * side
        sh = self.doc[b["page"]].new_shape()
        for s in g:
            F.ink(sh, [(cx + (x - (x0 + x1) / 2) * k, cy - (y - (y0 + y1) / 2) * k) for x, y in s],
                  max(0.55, self.pen * self.xh), self.color, self.rng)
        sh.commit()
        return self

    def cell(self, header, row, text, xh=None):
        """Write in a table cell: the column under `header`, data row 1, 2, …"""
        key = _norm(header)
        for p, cols, rows in self._tables():
            for i in range(len(cols) - 1):
                if key in _norm(self._cell_text(p, cols[i], cols[i + 1], rows[0], rows[1])):
                    if row + 1 >= len(rows):
                        raise KeyError(f"the table on page {p + 1} has no data row {row}")
                    x0, x1, y1 = cols[i], cols[i + 1], rows[row + 1]
                    xh = self._fit(text, x1 - x0 - 8, xh or min(self.xh, 4.0))
                    self._write(p, text, x0 + 4, y1 - 0.35 * xh - 3, xh)
                    self.log.append((header, round(xh, 2)))
                    return self
        raise KeyError(f"no table column called {header!r}")

    def _flow_height(self, text, width_pt, xh, line_gap):
        n = 0
        for para in text.split("\n"):
            x, n = 0.0, n + 1
            for w in para.split():
                adv = text_width(w) * xh * 1.06
                if x > 0 and x + adv > width_pt:
                    x, n = 0.0, n + 1
                x += adv + F.SPACE * xh
        return 2.3 * xh + (n - 1) * line_gap + 1.2 * xh

    def box(self, label, text, xh=None, pad=9):
        """Fill the big rectangle below a label: wrap, and shrink the writing if it does not fit."""
        s = self._label(label)
        cands = [r for p, r in self.rects if p == s["page"] and r.y0 >= s["bbox"].y0 - 2]
        if not cands:
            raise KeyError(f"no box found under {label!r}")
        r = min(cands, key=lambda r: r.y0)
        xh = xh or self.xh
        top = lambda xh: 1.3 * xh      # room above the first line: tall letters reach past the default start
        while xh > self.min_xh and self._flow_height(text, r.width - 2 * pad, xh, 3.9 * xh) > r.height - pad - top(xh):
            xh -= 0.1
        F.draw_pdf(self.doc[s["page"]], text, (r.x0 + pad, r.y0 + top(xh), r.x1 - pad, r.y1), xh_pt=xh, line_gap=3.9 * xh,
                   color=self.color, pen=self.pen, seed=self.rng.randrange(10 ** 6))
        self.log.append((label, round(xh, 2)))
        return self

    def comb(self, pno, x0, y0, x1, y1, text, n=None):
        """One character per box across a row of n equal boxes (dates, CURP, phone)."""
        n = n or len(text)
        cw = (x1 - x0) / n
        xh = min(self.xh, 0.42 * (y1 - y0), 0.55 * cw)
        for i, ch in enumerate(text[:n]):
            if ch == " ":
                continue
            w = text_width(ch) * xh
            self._write(pno, ch, x0 + i * cw + (cw - w) / 2, y1 - 0.25 * (y1 - y0), xh)
        return self

    def save(self, path):
        self.doc.save(path, garbage=3, deflate=True)
        return path


def preview(pdf, dpi=110):
    """Save every page of a PDF as a PNG next to it (name-1.png, name-2.png, …) and return the paths."""
    out = []
    for i, page in enumerate(pymupdf.open(pdf)):
        path = f"{pdf[:-4]}-{i + 1}.png"
        page.get_pixmap(dpi=dpi).save(path)
        out.append(path)
    return out


if __name__ == "__main__":
    for line in Form(sys.argv[1]).fields():
        print(line)
