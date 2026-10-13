"""Fill the test form by label, with no coordinates. -> out/forma_demo.pdf and page images."""
from forma import Form, preview

f = Form("tests/formato_prueba.pdf")
f.line("Nombre", "Juan Martín Cadena")
f.lines("Fecha", ["12", "10", "2026"])
f.line("Teléfono", "55 1234 5678")
f.check("Opción B")
f.cell("Concepto", 1, "Refrigerador")
f.cell("Monto", 1, "$1,250.00")
f.box("Comentarios", "El pago no se completó, pero el importe quedó retenido en mi tarjeta. "
                     "Solicito que se libere ese cargo y me confirmen por este medio.\nMuchas gracias por su ayuda.")
f.save("out/forma_demo.pdf")
print(preview("out/forma_demo.pdf"))
