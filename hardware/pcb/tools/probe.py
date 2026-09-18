import sexp,glob
F="/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
fps={"PHX":"TerminalBlock_Phoenix.pretty/TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal.kicad_mod",
"XH3":"Connector_JST.pretty/JST_XH_S3B-XH-A_1x03_P2.50mm_Horizontal.kicad_mod",
"XH4":"Connector_JST.pretty/JST_XH_S4B-XH-A_1x04_P2.50mm_Horizontal.kicad_mod",
"XH2":"Connector_JST.pretty/JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal.kicad_mod",
"PH3":"Connector_PinHeader_2.54mm.pretty/PinHeader_1x03_P2.54mm_Vertical.kicad_mod",
"FUSE":"Fuse.pretty/Fuse_1812_4532Metric.kicad_mod","CP":"Capacitor_THT.pretty/CP_Radial_D6.3mm_P2.50mm.kicad_mod",
"SOT":"Package_TO_SOT_SMD.pretty/SOT-23-3.kicad_mod","SMA":"Diode_SMD.pretty/D_SMA.kicad_mod","R":"Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod","LED":"LED_SMD.pretty/LED_0603_1608Metric.kicad_mod","MH":"MountingHole.pretty/MountingHole_3.2mm_M3.kicad_mod","SOCK":"Connector_PinSocket_2.54mm.pretty/PinSocket_1x19_P2.54mm_Vertical.kicad_mod"}
for k,p in fps.items():
    fp=sexp.load_footprint(F+p)
    xs=[];ys=[]
    for c in fp:
        if isinstance(c,list) and c[0] in('fp_line','fp_rect','fp_circle','fp_poly','fp_arc') and sexp.find1(c,'layer') and 'CrtYd' in sexp.find1(c,'layer')[1]:
            for pt in sexp.find(c,'start')+sexp.find(c,'end')+sexp.find(c,'center'):
                xs.append(float(pt[1]));ys.append(float(pt[2]))
            pts=sexp.find1(c,'pts')
            if pts:
                for xy in pts[1:]: xs.append(float(xy[1]));ys.append(float(xy[2]))
    pads=[(sexp.unq(c[1]),c[2],c[3],sexp.find1(c,'at')[1:],sexp.find1(c,'size')[1:],[sexp.unq(l) for l in sexp.find1(c,'layers')[1:]]) for c in sexp.find(fp,'pad')]
    print(k, "crtyd x[%.2f,%.2f] y[%.2f,%.2f]"%(min(xs),max(xs),min(ys),max(ys)) if xs else '', pads[:3])
S="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/"
for lib,name in [("Transistor_FET","AO3400A"),("Transistor_FET","AO3401A"),("Transistor_FET","BSS138"),("Diode","SS14"),("Device","R"),("Device","C"),("Device","C_Polarized"),("Device","Polyfuse"),("Device","LED"),("Connector_Generic","Conn_01x02"),("Connector_Generic","Conn_01x03"),("Connector_Generic","Conn_01x04"),("power","+5V"),("power","GND"),("Mechanical","MountingHole")]:
    s=sexp.load_symbol(S+lib+".kicad_sym",name)
    ext=sexp.find1(s,'extends')
    pins=[]
    for u in sexp.find(s,'symbol'):
        for p in sexp.find(u,'pin'):
            at=sexp.find1(p,'at'); pins.append((sexp.unq(sexp.find1(p,'number')[1]),sexp.unq(sexp.find1(p,'name')[1]),p[1],at[1],at[2],at[3],sexp.find1(p,'length')[1]))
    print(lib,name,'extends' if ext else '',sexp.find1(s,'property') and [ (sexp.unq(pp[1]),sexp.unq(pp[2])) for pp in sexp.find(s,'property') if pp[1] in('"Footprint"','"Reference"')],pins)
