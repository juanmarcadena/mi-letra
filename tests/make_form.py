"""Draw the blank form the tests and the demo fill: tests/formato_prueba.pdf."""
import pymupdf
SYM = "/System/Library/Fonts/Apple Symbols.ttf"     # has the empty-checkbox character
doc = pymupdf.open(); p = doc.new_page()
p.insert_text((60, 70), "Solicitud de prueba", fontsize=16)
p.insert_text((60, 110), "Nombre:", fontsize=10); p.draw_line((105, 112), (330, 112))
p.insert_text((60, 140), "Fecha:", fontsize=10)
for i, x in enumerate((100, 140, 180)):
    p.draw_line((x, 142), (x + 30, 142))
    if i < 2: p.insert_text((x + 33, 140), "/", fontsize=10)
p.insert_text((60, 170), "Teléfono:", fontsize=10); p.draw_line((110, 172), (260, 172))
for i, lab in enumerate(("Opción A", "Opción B", "Otra")):
    y = 205 + i * 18
    p.insert_text((60, y), "☐", fontsize=11, fontname="sym", fontfile=SYM)
    p.insert_text((74, y), lab, fontsize=10)
for i, h in enumerate(("Concepto", "Monto")):
    p.insert_text((70 + i * 200, 292), h, fontsize=9)
for y in (280, 298, 316, 334): p.draw_line((60, y), (460, y))
for x in (60, 260, 460): p.draw_line((x, 280), (x, 334))
p.insert_text((60, 372), "Comentarios:", fontsize=10); p.draw_rect(pymupdf.Rect(60, 380, 550, 560))
p.insert_text((60, 600), "Firma:", fontsize=10); p.draw_line((95, 602), (300, 602))
doc.save("tests/formato_prueba.pdf")
