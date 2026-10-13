"""Draw the same lines with two font files through macOS (CoreText) and stack them.
   python cmp_fonts.py A.ttf "LABEL A" B.ttf "LABEL B" out.png"""
import sys
import CoreText, Quartz
from Foundation import NSURL, NSAttributedString
L = ["Una vez que un banco confirma el pago, nunca hay ningún problema.",
     "El 11 de julio de 2011 pagué $1,111.00 MXN; folio ABC-1422.",
     "Juan Martín Cadena, Avenida de los Pinos 250, depto 1107.",
     "illa, fila, minimum, rr, tt, ff, oo, 00, 77, AV, To, Ya, P. J."]
a, la, b, lb, out = sys.argv[1:6]
if len(sys.argv) > 6:      # optional text file with the lines to draw
    L = [l.rstrip("\n") for l in open(sys.argv[6], encoding="utf-8") if l.strip()]
W, RH = 1700, 74
H = 2 * (len(L) * RH + 70) + 10
ctx = Quartz.CGBitmapContextCreate(None, W, H, 8, 0, Quartz.CGColorSpaceCreateDeviceRGB(), Quartz.kCGImageAlphaPremultipliedLast)
Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1); Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, W, H))
lab = CoreText.CTFontCreateWithName("Helvetica-Bold", 24, None)
y = H - 40
for path, label in ((a, la), (b, lb)):
    d = CoreText.CTFontManagerCreateFontDescriptorsFromURL(NSURL.fileURLWithPath_(path))
    font = CoreText.CTFontCreateWithFontDescriptor(d[0], 40, None)
    def put(t, f, col, yy):
        s = NSAttributedString.alloc().initWithString_attributes_(t, {CoreText.kCTFontAttributeName: f, CoreText.kCTForegroundColorAttributeName: Quartz.CGColorCreateGenericRGB(*col, 1)})
        Quartz.CGContextSetTextPosition(ctx, 20, yy); CoreText.CTLineDraw(CoreText.CTLineCreateWithAttributedString(s), ctx)
    put(label, lab, (0.8, 0, 0), y); y -= 62
    for t in L:
        put(t, font, (0.05, 0.1, 0.45), y); y -= RH
    y -= 8
dest = Quartz.CGImageDestinationCreateWithURL(NSURL.fileURLWithPath_(out), "public.png", 1, None)
Quartz.CGImageDestinationAddImage(dest, Quartz.CGBitmapContextCreateImage(ctx), None); print("saved", Quartz.CGImageDestinationFinalize(dest))
