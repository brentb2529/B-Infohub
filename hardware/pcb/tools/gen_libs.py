"""Write project footprints into binfohub.pretty/ plus the lib tables.

Rev 1.1 footprints:
  ESP32-WROOM-32E_edge  -- KiCad's stock RF_Module:ESP32-WROOM-32E with the
                           antenna courtyard and copper keepout narrowed from
                           +-24 mm to +-12 mm across the antenna. The module
                           sits at the board edge, antenna outward, and the
                           stock width would swallow a mounting hole. Pads,
                           thermal via array, silk and fab are untouched.
  SW_TS-1187A           -- XKB TS-1187A 5.1 x 5.1 mm 4-pad tactile switch
                           (JLC basic C318884). Pads numbered so that only the
                           two DIAGONAL pads (1, 2) carry a net; 3 and 4 are
                           unassigned. See circuit.py, SW1.
The rev 1.0 DevKitC footprint is kept in the directory for history; nothing
references it.
"""
import sexp, os, copy
from sexp import q, find, find1, unq
from circuit import uid, LIBS

ANT_HALF=12.0   # +- mm across the antenna; stock is 24

def wroom_edge():
    fp=sexp.load_footprint(LIBS+"footprints/RF_Module.pretty/ESP32-WROOM-32E.kicad_mod")
    fp=copy.deepcopy(fp); fp[1]=q("ESP32-WROOM-32E_edge")
    d=find1(fp,'descr')
    if d: d[1]=q(unq(d[1])+" -- b-infohub: antenna courtyard/keepout narrowed to +-%g mm for an edge placement"%ANT_HALF)
    def clamp(pts):
        for p in pts[1:]:
            x=float(p[1])
            if x<=-ANT_HALF: p[1]=f"{-ANT_HALF:g}"
            elif x>=ANT_HALF: p[1]=f"{ANT_HALF:g}"
    for c in fp:
        if isinstance(c,list) and c[0]=='fp_poly' and unq(find1(c,'layer')[1])=='F.CrtYd':
            # the antenna wing of the courtyard is every vertex beyond the body width
            for p in find1(c,'pts')[1:]:
                x=float(p[1])
                if abs(x)>10: p[1]=f"{ANT_HALF if x>0 else -ANT_HALF:g}"
        if isinstance(c,list) and c[0]=='zone':
            clamp(find1(find1(c,'polygon'),'pts'))
        # thermal-pad vias: the stock footprint drills 0.2 mm, under JLC's
        # standard 0.3 mm minimum (and this project's DRC rule). 0.3 in a 0.6
        # pad keeps the 0.15 mm annular ring the rules ask for.
        if isinstance(c,list) and c[0]=='pad' and c[2]=='thru_hole':
            d=find1(c,'drill')
            if d and float(d[1])<0.3: d[1]='0.3'
    return fp

def ts1187a():
    """XKB TS-1187A: 5.1 x 5.1 body, four pads 1.5 x 1.0 at (+-3.25, +-1.85)."""
    fp=['footprint',q("SW_TS-1187A"),['version','20241229'],['generator',q('binfohub_gen')],['layer',q('F.Cu')],
        ['descr',q("XKB TS-1187A-B-A-B 5.1x5.1 mm SMD tactile switch; pads 1/2 are the diagonal pair used, 3/4 unassigned")],
        ['tags',q("tactile switch SMD")],['attr','smd']]
    def prop(n,v,y,hide,layer="F.Fab"):
        e=['effects',['font',['size','1','1'],['thickness','0.15']]]
        if hide: e.append(['hide','yes'])
        return ['property',q(n),q(v),['at','0',str(y),'0'],['layer',q(layer)],['uuid',q(uid('swprop',n))],e]
    fp+=[prop("Reference","REF**",-4.2,False,"F.SilkS"),prop("Value","SW_TS-1187A",4.2,False),prop("Datasheet","",0,True),prop("Description","",0,True)]
    def rect(layer,hx,hy,w=0.12):
        return ['fp_rect',['start',f"{-hx}",f"{-hy}"],['end',f"{hx}",f"{hy}"],['stroke',['width',str(w)],['type','solid']],['fill','no'],['layer',q(layer)],['uuid',q(uid('swrect',layer))]]
    fp.append(rect("F.Fab",2.55,2.55,0.1)); fp.append(rect("F.CrtYd",4.3,3.0,0.05))
    # silk: body outline broken where the pads are
    for y in (-2.55,2.55):
        fp.append(['fp_line',['start','-2.2',f"{y}"],['end','2.2',f"{y}"],['stroke',['width','0.12'],['type','solid']],['layer',q('F.SilkS')],['uuid',q(uid('swline',y))]])
    fp.append(['fp_circle',['center','0','0'],['end','1.5','0'],['stroke',['width','0.12'],['type','solid']],['fill','no'],['layer',q('F.SilkS')],['uuid',q(uid('swcirc'))]])
    fp.append(['fp_text','user',q("${REFERENCE}"),['at','0','0','0'],['layer',q('F.Fab')],['uuid',q(uid('swreft'))],['effects',['font',['size','0.8','0.8'],['thickness','0.12']]]])
    # pad numbering: 1 top-left, 2 bottom-right (the used diagonal), 3 top-right, 4 bottom-left
    for num,(x,y) in {"1":(-3.25,-1.85),"2":(3.25,1.85),"3":(3.25,-1.85),"4":(-3.25,1.85)}.items():
        fp.append(['pad',q(num),'smd','rect',['at',f"{x}",f"{y}"],['size','1.5','1.0'],['layers',q('F.Cu'),q('F.Paste'),q('F.Mask')],['uuid',q(uid('swpad',num))]])
    fp.append(['embedded_fonts','no'])
    return fp

def write(d):
    os.makedirs(d+"/binfohub.pretty",exist_ok=True)
    open(d+"/binfohub.pretty/ESP32-WROOM-32E_edge.kicad_mod","w").write(sexp.dump(wroom_edge())+"\n")
    open(d+"/binfohub.pretty/SW_TS-1187A.kicad_mod","w").write(sexp.dump(ts1187a())+"\n")
    open(d+"/sym-lib-table","w").write('(sym_lib_table\n  (version 7)\n  (lib (name "binfohub")(type "KiCad")(uri "${KIPRJMOD}/binfohub.kicad_sym")(options "")(descr "b-infohub project symbols"))\n)\n')
    open(d+"/fp-lib-table","w").write('(fp_lib_table\n  (version 7)\n  (lib (name "binfohub")(type "KiCad")(uri "${KIPRJMOD}/binfohub.pretty")(options "")(descr "b-infohub project footprints"))\n)\n')
if __name__=="__main__": write("..")
