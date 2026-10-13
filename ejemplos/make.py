"""Draw the example images shown in the README. Run from the project folder:
   PYTHONPATH=. uv run --with-requirements requirements.txt python3 ejemplos/make.py"""
import pymupdf
import CoreText, Quartz
from Foundation import NSURL, NSAttributedString
from PIL import Image, ImageDraw, ImageFont
import avgfont as F
from forma import Form

INK = (0.05, 0.1, 0.45)
LABEL = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)


def typeset(out, rows, size=44, width=1500, row_h=92, drop=66):
    """rows: (font file, label, text). Drawn by macOS, the way any app would draw the fonts."""
    H = len(rows) * row_h + 24
    ctx = Quartz.CGBitmapContextCreate(None, width, H, 8, 0, Quartz.CGColorSpaceCreateDeviceRGB(), Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, width, H))
    lab = CoreText.CTFontCreateWithName("Helvetica", 15, None)

    def put(text, font, col, x, y):
        s = NSAttributedString.alloc().initWithString_attributes_(text, {CoreText.kCTFontAttributeName: font, CoreText.kCTForegroundColorAttributeName: Quartz.CGColorCreateGenericRGB(*col, 1)})
        Quartz.CGContextSetTextPosition(ctx, x, y)
        CoreText.CTLineDraw(CoreText.CTLineCreateWithAttributedString(s), ctx)

    for i, (path, label, text) in enumerate(rows):
        top = H - 12 - i * row_h
        d = CoreText.CTFontManagerCreateFontDescriptorsFromURL(NSURL.fileURLWithPath_(path))
        put(label, lab, (0.55, 0.55, 0.55), 16, top - 18)
        put(text, CoreText.CTFontCreateWithFontDescriptor(d[0], size, None), INK, 16, top - drop)
    dest = Quartz.CGImageDestinationCreateWithURL(NSURL.fileURLWithPath_(out), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, Quartz.CGBitmapContextCreateImage(ctx), None)
    Quartz.CGImageDestinationFinalize(dest)


PAN = "El veloz murciélago hindú comía feliz cardillo y kiwi."
typeset("ejemplos/estilos.png", [
    ("out/LetraJuan.ttf", "Letra Juan", PAN),
    ("out/LetraJuan-Bold.ttf", "Letra Juan Bold", PAN),
    ("out/LetraJuan-Italic.ttf", "Letra Juan Italic", PAN),
    ("out/LetraJuanCursiva.ttf", "Letra Juan Cursiva", "The other one is better, however there were more tickets."),
    ("out/LetraJuanCursiva-Italic.ttf", "Letra Juan Cursiva Italic", "The other one is better, however there were more tickets."),
])
typeset("ejemplos/variantes.png", [
    ("out/LetraJuan.ttf", "Seven versions of every letter rotate as you type, so repeats never match", "banana banana banana   de de de de de de"),
], size=58, row_h=120)
typeset("ejemplos/presion.png", [("out/LetraJuan.ttf", "Strokes thin where the pen lands and lifts", "Gracias, Juan")], size=120, width=1250, row_h=215, drop=150)

# a filled form
f = Form("tests/formato_prueba.pdf")
f.line("Nombre", "Juan Martín Cadena").lines("Fecha", ["12", "10", "2026"]).line("Teléfono", "55 1234 5678").check("Opción B")
f.cell("Concepto", 1, "Refrigerador").cell("Monto", 1, "$1,250.00")
f.box("Comentarios", "El pago no se completó, pero el importe quedó retenido en mi tarjeta. Solicito que se libere ese cargo y me confirmen por este medio.\nMuchas gracias por su ayuda.")
x = f.doc[0].get_pixmap(dpi=120, clip=pymupdf.Rect(40, 40, 572, 590))
Image.frombytes("RGB", (x.width, x.height), x.samples).save("ejemplos/formulario.png")

# a cursive note
F.use_style("cursiva")
doc = pymupdf.open(); page = doc.new_page(width=460, height=170)
F.draw_pdf(page, "Querida abuela:\nGracias por la receta del domingo. Me salió casi tan rica como la tuya, aunque todavía me falta práctica con la masa.\nUn abrazo fuerte, nos vemos en diciembre.", (28, 8, 432, 165), xh_pt=6.2)
x = page.get_pixmap(dpi=170)
Image.frombytes("RGB", (x.width, x.height), x.samples).save("ejemplos/nota.png")
F.use_style("molde")

# how a letter is made: ten real samples, and the average of its group
S, xh, RH = 2, 40, 190
letters = "aeg"
small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18 * S)
img = Image.new("RGB", (1500 * S, len(letters) * RH * S), "white"); d = ImageDraw.Draw(img)
for r, ch in enumerate(letters):
    c = F.A[ch]["cands"][F.A[ch]["chosen"]]
    y = (r * RH + 105) * S
    for i, inst in enumerate(c["insts"][:10]):
        g = [s - [min(q[:, 0].min() for q in inst), 0] for s in inst]
        F.draw(d, g, (30 + i * 105) * S, y, xh * S, 3 * S, fill=(150, 150, 150))
    ax, ay = 1095 * S, y - 20 * S                      # arrow
    d.line([(ax, ay), (ax + 60 * S, ay)], fill=(120, 120, 120), width=3 * S)
    d.polygon([(ax + 60 * S, ay - 9 * S), (ax + 78 * S, ay), (ax + 60 * S, ay + 9 * S)], fill=(120, 120, 120))
    m = [s - [min(q[:, 0].min() for q in c["mean"]), 0] for s in c["mean"]]
    F.draw(d, m, 1200 * S, y, xh * 1.5 * S, 5 * S, fill=(15, 25, 115))
    d.text((1310 * S, y - 32 * S), f"average of {c['n']}", fill=(120, 120, 120), font=small)
img.resize((1500, len(letters) * RH), Image.LANCZOS).save("ejemplos/promedio.png")
print("ok")
