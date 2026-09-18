"""Write bom_jlc.csv / cpl_jlc.csv from circuit.py. U1 (ESP32 module) becomes two 1x19 female socket rows U1A/U1B placed by JLC."""
import csv
from circuit import *
SOCK_LCSC="C319202"
# JLCPCB's part library is rotated relative to KiCad's footprints for these packages. Verified in the JLC
# placement preview on 2026-08-25 (pin-1 mark vs. our copper): SOT-23 needs +180, TSOT-23-6 needs -90 (=270),
# 1xN pin headers need 90, CP_Elec SMD electrolytic needs 180 (JLC "+" opposite to KiCad pad 1). Everything else (0603/0805/1206, SMA, SOD-123, LED 0603, JST-XH, 5.08 terminals,
# 1x19 sockets, SRN6045 inductor, 1812 fuse) matched as-is.
ROT_FIX={"SOT":180,"TSOT6":270,"PH4":90,"PH3":90,"CPSMD":180}   # PHX4/PHX8 (KF128 2.54 terminals): verified 0 in the JLC viewer
rows={}
descs={}
for ref,p in sorted(P.items(), key=lambda kv:(kv[0][0],int(''.join(c for c in kv[0][1:] if c.isdigit()) or 0))):
    if ref.startswith("H"): continue
    if ref=="U1":
        k=("Female header 1x19 2.54mm","PinSocket_1x19_P2.54mm_Vertical",SOCK_LCSC)
        rows[k]=["U1A","U1B"]; descs[k]=["ESP32 socket row"]; continue
    # Group by VALUE + FOOTPRINT + LCSC only. The description must NOT be part of the
    # key: five identical 100 nF caps with five different per-net comments would
    # otherwise become five BOM lines, and JLC flags that as "multiple lines matched to
    # the same part" and deselects the duplicates. Caught in the JLC BOM review,
    # 2026-08-31.
    key=(p["value"],FP[p["fp"]][1],"" if p["dnp"] else p["lcsc"])
    rows.setdefault(key,[]).append(ref)
    descs.setdefault(key,[]).append(p["desc"])
with open("../bom_jlc.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["Comment","Designator","Footprint","LCSC Part #","Qty","Assembly","Note","Description"])
    for key,refs in rows.items():
        val,fp,lcsc = key
        # keep the longest description: it is the one carrying the reasoning
        desc = max(descs[key], key=len)
        asm="DNP" if not lcsc else ("JLC THT (economic, hand-solder fee)" if any(P.get(r,{}).get("hand") or r.startswith("U1") for r in refs) else "JLC SMT")
        w.writerow([val,",".join(refs),fp,lcsc,len(refs),asm,"",desc])
with open("../cpl_jlc.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["Designator","Mid X","Mid Y","Layer","Rotation"])
    for ref,p in sorted(P.items()):
        if ref.startswith("H") or p["dnp"]: continue
        x,y,r=p["pcb"]
        if ref=="U1":
            w.writerow(["U1A",f"{x:.3f}mm",f"{-(y-12.7):.3f}mm","Top","0.000000"]); w.writerow(["U1B",f"{x:.3f}mm",f"{-(y+12.7):.3f}mm","Top","0.000000"]); continue
        r=(r+ROT_FIX.get(p["fp"],0))%360
        w.writerow([ref,f"{x:.3f}mm",f"{-y:.3f}mm","Top",f"{r:.6f}"])
print("bom rows",len(rows))
