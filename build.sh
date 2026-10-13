#!/bin/zsh
# One command to rebuild the handwriting from scratch and install the font.
#   ./build.sh            rebuild from the frozen copy of the notes (data/raw)
#   ./build.sh live       re-read the live Notability notes first
#   ./build.sh verify     also redo the second-opinion reading (changes which samples are trusted)
#   ./build.sh font       only rebuild and install the font from the current letters
set -e
cd "$(dirname "$0")"
run() { uv run --quiet --with-requirements requirements.txt python3 "$@"; }
if [[ "$1" != "font" && "$1" != "install" || "$1" == "" ]]; then
  if [[ "$1" == "live" ]]; then run snapshot_raw.py; fi
  export LETRA_RAW=1
  run extract.py          # cut words and letters out of the notes
  run bank.py             # normalise, score letters
  # data/ocr.pkl (the second opinion from Apple's recogniser) is a frozen input: re-reading
  # the words gives a slightly different answer each time the rendering changes, which
  # reshuffles the letter groups. Only refresh it on purpose.
  if [[ "$1" == "verify" || ! -f data/ocr.pkl ]]; then run verify.py; run bank.py; fi
  for c in 'J' '#&*' '[]>×→✓✗_~{}•'; do run pick.py "$c" out/_pick_tmp.png 200 >/dev/null; done; rm -f out/_pick_tmp.png   # raw samples the manual picks refer to
  run avg.py              # average each letter; applies the choices recorded in avg.py
fi
run avgfont.py all 0.35           # Letra Juan and Letra Juan Cursiva, each in Regular, Bold, Italic and Bold Italic
run make_profile.py "$HOME/Documents/me/Letra Juan - iPhone y iPad"   # the same fonts packaged for iPhone and iPad
run test_forma.py                 # form-filler checks: box text stays inside, field list is clean
run measure.py read
# Installing is a separate, deliberate step: a rebuild that scores worse must not replace the font in use.
if [[ "${@[-1]}" == "install" ]]; then
  rm -f ~/Library/Fonts/LetraJuan*.ttf; sleep 2
  cp out/LetraJuan.ttf out/LetraJuan-*.ttf out/LetraJuanCursiva*.ttf ~/Library/Fonts/
  echo "Installed. Quit and reopen any app that had the font loaded."
else
  echo "Built the eight font files in out/ (not installed). Add 'install' as the last word to install it."
fi
