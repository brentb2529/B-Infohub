#!/bin/sh
# Rebuild every deliverable from the routed board: ERC, DRC, BOM/CPL, gerbers
# + drill, the JLC zip and the preview renders. Run from tools/ after router.py
# (or rebuild.py for text-only edits). Exit status is non-zero if ERC or DRC
# reports an error-severity violation.
set -e
cd "$(dirname "$0")"
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
P=binfohub_bridge
cd ..
echo "== ERC";  $K sch erc --severity-all -o $P-erc.rpt $P.kicad_sch 2>&1 | grep -v mtime
echo "== DRC";  $K pcb drc --severity-all --refill-zones --schematic-parity -o $P-drc.rpt $P.kicad_pcb 2>&1 | grep -v mtime
echo "== BOM";  (cd tools && python3 gen_bom.py)
echo "== gerbers"
rm -rf gerbers && mkdir gerbers
# --check-zones: the generated board file carries zone OUTLINES only (gen_pcb.py
# writes no fill polygons), so without a refill at plot time the gerbers have no
# ground pour. Rev 1.0's shipped gerbers were plotted that way -- zero G36
# regions in F_Cu -- so the fielded board's GND is tracks only. Verified by
# counting G36 below.
$K pcb export gerbers --check-zones --no-protel-ext --subtract-soldermask \
   --layers F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
   -o gerbers/ $P.kicad_pcb 2>&1 | grep -v mtime
echo "pour regions (G36) in F_Cu: $(grep -c G36 gerbers/$P-F_Cu.gbr), B_Cu: $(grep -c G36 gerbers/$P-B_Cu.gbr)"
echo "gerber files: $(ls gerbers | wc -l | tr -d ' ')"
$K pcb export drill --format excellon --excellon-units mm -o gerbers/ $P.kicad_pcb 2>&1 | grep -v mtime
rm -f ${P}_jlc.zip && (cd gerbers && zip -q ../${P}_jlc.zip ./*)
echo "== previews"
mkdir -p preview
$K pcb render --side top    --background opaque --zoom 1.0 -w 2000 -h 2000 -o preview/top.png    $P.kicad_pcb 2>&1 | grep -v mtime
$K pcb render --side bottom --background opaque --zoom 1.0 -w 2000 -h 2000 -o preview/bottom.png $P.kicad_pcb 2>&1 | grep -v mtime
$K pcb export pdf --layers F.SilkS,F.Cu,Edge.Cuts,F.Fab -o preview/silk_front.pdf $P.kicad_pcb 2>&1 | grep -v mtime
$K pcb export pdf --layers F.Fab,F.CrtYd,Edge.Cuts -o preview/fab_front.pdf $P.kicad_pcb 2>&1 | grep -v mtime
$K pcb export pdf --layers B.SilkS,Edge.Cuts --mirror -o preview/silk_back.pdf $P.kicad_pcb 2>&1 | grep -v mtime
$K sch export pdf -o preview/schematic.pdf $P.kicad_sch 2>&1 | grep -v mtime
echo "== summary"
echo "ERC: $(grep -c '^\[' $P-erc.rpt) violations"
echo "DRC: $(grep -cE '; error$' $P-drc.rpt) errors, $(grep -cE '; warning$' $P-drc.rpt) warnings, $(grep -c '^\[unconnected_items\]' $P-drc.rpt) unconnected"
test "$(grep -cE '; error$' $P-drc.rpt)" = 0 && test "$(grep -c '^\[' $P-erc.rpt)" = 0
