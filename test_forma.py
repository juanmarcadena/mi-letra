"""Checks for the form filler. Run: uv run --with-requirements requirements.txt python3 test_forma.py"""
from forma import Form, INK

BLANK = "tests/formato_prueba.pdf"      # drawn by tests/make_form.py


def ink_rects(page):
    return [d["rect"] for d in page.get_drawings() if d.get("fill") and all(abs(a - b) < 0.02 for a, b in zip(d["fill"], INK))]


def test_box_text_stays_inside():
    for text in ("Esta es una prueba de mi letra en un formato real.", "El pago no se completó. " * 30):
        f = Form(BLANK)
        f.box("Comentarios", text)
        box = f.rects[0][1]
        out = [r for r in ink_rects(f.doc[0]) if not (r.x0 >= box.x0 and r.x1 <= box.x1 and r.y0 >= box.y0 and r.y1 <= box.y1)]
        assert not out, f"{len(out)} strokes outside the box, e.g. {out[0]} vs {box}"


def test_date_lists_three_lines():
    rows = [r for r in Form(BLANK).fields() if "(30 pt wide)" in r]
    assert len(rows) == 3, f"day / month / year should be three lines, got {len(rows)}: {rows}"


def test_every_kind_of_field_fills():
    f = Form(BLANK)
    f.line("Nombre", "Juan Martín Cadena").lines("Fecha", ["12", "10", "2026"]).check("Opción B")
    f.cell("Monto", 1, "$1,250.00").box("Comentarios", "texto")
    assert len(ink_rects(f.doc[0])) > 40


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
