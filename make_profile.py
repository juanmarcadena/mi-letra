"""Package the eight font files as an Apple configuration profile, the way fonts are
installed on iPhone and iPad.   python make_profile.py [output folder]
Open the .mobileconfig on the device, then Settings > General > VPN & Device Management."""
import os, plistlib, sys, uuid
NS = uuid.UUID("6f1d2c1e-5a0b-4c57-9c3e-2f6b1f1a7e10")
FILES = ["LetraJuan.ttf", "LetraJuan-Bold.ttf", "LetraJuan-Italic.ttf", "LetraJuan-BoldItalic.ttf",
         "LetraJuanCursiva.ttf", "LetraJuanCursiva-Bold.ttf", "LetraJuanCursiva-Italic.ttf", "LetraJuanCursiva-BoldItalic.ttf"]
ident = "mx.juancadena.letrajuan"
content = []
for fn in FILES:
    data = open(os.path.join("out", fn), "rb").read()
    content.append({"PayloadType": "com.apple.font", "PayloadVersion": 1,
                    "PayloadIdentifier": f"{ident}.{fn[:-4].lower()}", "PayloadUUID": str(uuid.uuid5(NS, fn)).upper(),
                    "PayloadDisplayName": fn[:-4], "Name": fn, "Font": data})
profile = {"PayloadType": "Configuration", "PayloadVersion": 1, "PayloadIdentifier": ident,
           "PayloadUUID": str(uuid.uuid5(NS, "profile")).upper(), "PayloadDisplayName": "Letra Juan",
           "PayloadDescription": "Letra Juan y Letra Juan Cursiva: la letra de Juan Martín Cadena, en Regular, Bold, Italic y Bold Italic.",
           "PayloadOrganization": "Juan Martín Cadena", "PayloadContent": content}
out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
os.makedirs(out_dir, exist_ok=True)
path = os.path.join(out_dir, "Letra Juan (iPhone y iPad).mobileconfig")
plistlib.dump(profile, open(path, "wb"))
print(path, "|", len(content), "fonts |", round(os.path.getsize(path) / 1e6, 1), "MB")
