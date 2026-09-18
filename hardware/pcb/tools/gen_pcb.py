"""Generate binfohub_bridge.kicad_pcb (footprints placed, nets assigned, zones, silkscreen); routing added by router.py"""
import math, copy, json, sexp
from sexp import q, unq, find, find1
from circuit import *

FPDIR=LIBS+"footprints/"
# Screw-terminal footprints whose mechanical locating pegs must be removed.
# We borrow KiCad's Phoenix MPT/MKDS footprints because they are pitch-compatible
# with the KF128/KF301 parts we actually buy -- but a KF128 has ONLY solder pins, no
# locating pegs. KiCad's own library is inconsistent here too: the 2- and 3-way MPT
# footprints carry pegs and the 4-way does not, so leaving them would drill two empty
# holes beside J2 and none beside J3. Strip them from all of them.
_PEGLESS_TERMINALS = {"PHX", "XH2", "XH3", "XH4"}

def load_fp(short):
    lib,name=FP[short]
    path=("../binfohub.pretty/"+name+".kicad_mod") if lib=="binfohub" else FPDIR+lib+".pretty/"+name+".kicad_mod"
    fp=sexp.load_footprint(path)
    if short in _PEGLESS_TERMINALS:
        fp[:]=[c for c in fp if not (isinstance(c,list) and c[0]=="pad"
                                     and len(c)>2 and c[2]=="np_thru_hole")]
    return fp

def rot(px,py,r):
    c=math.cos(math.radians(r)); s=math.sin(math.radians(r)); return (px*c-py*s, px*s+py*c)   # KiCad pcb: y down, angle CCW on screen => use (x,y)->(xc+ys, -xs+yc)
def fp_to_board(px,py,r,X,Y):
    a=math.radians(r); c=math.cos(a); s=math.sin(a)
    return (X+px*c+py*s, Y-px*s+py*c)

def set_at(node,x,y,r):
    at=find1(node,'at')
    if at: at[:]=['at',f"{x:.4f}",f"{y:.4f}",f"{r:g}"]
    else: node.insert(3,['at',f"{x:.4f}",f"{y:.4f}",f"{r:g}"])

def build_footprint(ref,netidx):
    p=P[ref]; lib,name=FP[p["fp"]]; X,Y,R=p["pcb"]
    fp=copy.deepcopy(load_fp(p["fp"])); fp[1]=q(lib+":"+name)
    # strip version/generator lines that belong to lib file? keep them - KiCad accepts
    # insert layer/uuid/at right after name
    body=[c for c in fp[2:] if not (isinstance(c,list) and c[0] in('layer','at','uuid','path','sheetname','sheetfile','property','embedded_fonts'))]
    props={unq(c[1]):c for c in fp if isinstance(c,list) and c[0]=='property'}
    head=['footprint',fp[1],['layer',q('F.Cu')],['uuid',q(uid('fp',ref))],['at',f"{X}",f"{Y}",f"{R:g}"],
          ['path',q('/'+ROOT_UUID+'/'+uid('sym',ref))],['sheetname',q('/')],['sheetfile',q(PROJECT+'.kicad_sch')]]
    if p["dnp"]:
        ex=[c for c in body if isinstance(c,list) and c[0]=='attr']
        body=[c for c in body if not(isinstance(c,list) and c[0]=='attr')]
        head.append(['attr']+([x for x in ex[0][1:]] if ex else ['smd'])+['dnp'])
    def prop(nm,val,src,hide=None):
        n=copy.deepcopy(src) if src else ['property',q(nm),q(val),['at','0','0','0'],['layer',q('F.Fab')],['effects',['font',['size','1','1'],['thickness','0.15']]]]
        n[1]=q(nm); n[2]=q(val)
        if not find1(n,'uuid'): n.append(['uuid',q(uid('prop',ref,nm))])
        else: find1(n,'uuid')[1]=q(uid('prop',ref,nm))
        at=find1(n,'at'); 
        if at and len(at)>3: at[3]=f"{(float(at[3])+R)%360:g}"
        elif at: at.append(f"{R:g}")
        if hide is not None:
            n=[c for c in n if not(isinstance(c,list) and c[0]=='hide')]
            if hide: n.insert(4,['hide','yes'])
        return n
    rp=prop("Reference",ref,props.get("Reference"),hide=False); find1(rp,"layer")[1]=q("F.Fab"); head.append(rp)
    head.append(prop("Value",p["value"],props.get("Value")))
    head.append(prop("Footprint",lib+":"+name,props.get("Footprint")))
    head.append(prop("Datasheet","",props.get("Datasheet")))
    head.append(prop("Description",p["desc"],props.get("Description")))
    head.append(prop("LCSC",p["lcsc"],None,hide=True))
    out=head
    for c in body:
        if isinstance(c,list) and c[0]=='pad':
            padno=unq(c[1]); at=find1(c,'at')
            if len(at)>3: at[3]=f"{(float(at[3])+R)%360:g}"
            else: at.append(f"{R:g}")
            net=p["pins"].get(int(padno)) if padno.isdigit() else None
            if ref=="U1" and net is None: net=unconnected_nets()[int(padno)]
            if net:
                i=[k for k,x in enumerate(c) if isinstance(x,list) and x[0]=='layers'][0]
                c.insert(i+1,['net',str(netidx[net]),q(net)])
            if not find1(c,'uuid'): c.append(['uuid',q(uid('pad',ref,padno,len(out)))])
        elif isinstance(c,list) and c[0] in('fp_text',):
            at=find1(c,'at')
            if len(at)>3: at[3]=f"{(float(at[3])+R)%360:g}"
            else: at.append(f"{R:g}")
            if not find1(c,'uuid'): c.append(['uuid',q(uid('fpt',ref,len(out)))])
        elif isinstance(c,list) and c[0].startswith('fp_') and not find1(c,'uuid'):
            c.append(['uuid',q(uid('fpg',ref,len(out)))])
        elif isinstance(c,list) and c[0] in('version','generator','generator_version'): continue
        out.append(c)
    return out

def pad_geoms(ref):
    """board-space pad geometry: list of dict(net, x, y, w, h, rot, shape, tht)"""
    p=P[ref]; X,Y,R=p["pcb"]; fp=load_fp(p["fp"]); res=[]
    for c in find(fp,'pad'):
        at=find1(c,'at'); px,py=float(at[1]),float(at[2]); pr=float(at[3]) if len(at)>3 else 0
        sz=find1(c,'size'); w,h=float(sz[1]),float(sz[2])
        bx,by=fp_to_board(px,py,R,X,Y)
        padno=unq(c[1]); net=p["pins"].get(int(padno)) if padno.isdigit() else None
        res.append(dict(ref=ref,pad=padno,net=net,x=bx,y=by,w=w,h=h,rot=(pr+R)%360,shape=c[3],tht=c[2]!='smd',drill=float(find1(c,'drill')[1]) if find1(c,'drill') else 0))
    return res

SILK=[]  # (text, x, y, rot, size)
def silk(t,x,y,r=0,s=1.0,layer="F.SilkS"): SILK.append((t,x,y,r,s,layer))

# Pin labels must sit over their OWN pad, not be packed into one centred string.
# Measured on the previous revision: J3's "12V" glyph landed 4.12 mm from its pad --
# more than 1.5 pin pitches -- because a centred "12V GND A B" spreads its tokens by
# text metrics, not by pitch. Wiring +12 V into the A terminal on that basis would
# destroy a transceiver. Positions here are derived from the placed geometry, so they
# cannot drift from the pads.
_TERM_PITCH_SILK = {"PHX": 5.08, "XH2": 2.54, "XH3": 2.54, "XH4": 2.54}

def term_pin_labels(ref, labels, dy=1.9, size=0.62):
    """Place one silk label per terminal pin, in ORIGINAL pin order (1..N).

    circuit.py's orientation post-pass rotates each block 180 deg about its own pad
    row, so the anchor ends up on original pin N and pads run back in -x. Original
    pin i therefore sits at anchor_x - (N-i)*pitch.
    """
    part = P[ref]
    pitch = _TERM_PITCH_SILK[part["fp"]]
    ax, ay, _ = part["pcb"]
    n = len(labels)
    for i, text in enumerate(labels, start=1):
        silk(text, ax - (n - i) * pitch, ay + dy, 0, size)

def header_pin_labels(ref, labels, dx=-2.6, pitch=2.54, size=0.62):
    """One label per pin for a vertical 1xN header (pads run +y from the anchor)."""
    ax, ay, _ = P[ref]["pcb"]
    for i, text in enumerate(labels):
        silk(text, ax + dx, ay + i * pitch, 0, size)


def silkscreen():
    """Front = what you need while wiring. Back = why.

    The front of this board is dense with parts and auto-placed reference
    designators; the back is bare copper-free space. Explanatory text therefore
    lives on B.SilkS, where it is legible with the board in your hand and cannot
    collide with a pad or a refdes.
    """
    B="B.SilkS"

    # ---------- FRONT: wiring only ----------
    # Title sits along the bottom edge: the middle of the board is the ESP32
    # module, whose footprint carries its own pin-name silk.
    silk("B-INFOHUB BRIDGE v1.0", 45, 89.8, 0, 1.0)

    # Terminal labels sit BELOW each block, clear of its footprint outline.
    # Polarity is marked per pad rather than as a floating +/- pair.
    silk("J1 12V IN", 14.5, 14.6, 0, 0.9)
    term_pin_labels("J1", ["+", "-"], dy=9.6, size=1.0)

    silk("J2 BUS", 51.3, 14.6, 0, 0.9)
    term_pin_labels("J2", ["A", "B"], dy=9.6)

    silk("J3 INFOHUB", 73.8, 14.6, 0, 0.9)
    term_pin_labels("J3", ["12V", "GND", "A", "B"], dy=9.6)

    silk("JP1 TERM", 62.5, 25.0, 0, 0.65)
    silk("JP2 TERM", 82.5, 25.0, 0, 0.65)

    for x, lab, col in [(18.0,"PWR","green"), (29.0,"WIFI","blue"), (40.0,"BUS","green"),
                        (51.0,"FAULT","red"), (62.0,"TX","yellow")]:
        silk(lab, x, 84.0, 0, 0.8)
        silk(col, x, 86.2, 0, 0.65)

    # J4 pin 1 (GND) is at the TOP (y=54) and pin 6 (TX) at the bottom (y=66.7).
    # Text rotated 90 deg renders FIRST character at the BOTTOM, so the legend has to
    # be written in reverse pin order to line up. Written forwards it reads
    # G-P-W-B-F-T bottom-to-top and points every wire at the wrong pin.
    silk("J4 EXT LED", 80.4, 60.0, 90, 0.7)
    header_pin_labels("J4", ["G", "P", "W", "B", "F", "T"], dx=-2.2)
    silk("1", 82.2, 51.9, 0, 0.8)

    # ---------- BACK: everything else ----------
    silk("B-INFOHUB BRIDGE  v1.0", 45, 12, 0, 2.4, B)
    silk("Briggs & Stratton GC-1032 -> Home Assistant", 45, 17, 0, 1.1, B)
    silk("2026-08  bbensten", 45, 21, 0, 0.9, B)

    silk("CONTROLLER: SLAVE 10   9600 8E1", 45, 30, 0, 1.3, B)
    silk("measured on the unit, NOT the genmon default of 1 / 19200", 45, 34, 0, 0.8, B)

    silk("J1  12V DC ONLY - NEVER 24VAC", 45, 38, 0, 1.0, B)
    silk("J2  to ABC controller: A and B only (harness GND lands on J1).", 45, 46, 0, 0.8, B)
    silk("     Swap A/B if the bus stays silent - it cannot damage anything.", 45, 50, 0, 0.8, B)
    silk("J3  to InfoHub: +12V (fused by F2, 2A), GND, A, B", 45, 54, 0, 0.8, B)
    silk("F1 1.1A feeds the bridge, F2 2A feeds the InfoHub - separate on purpose:", 45, 58, 0, 0.8, B)
    silk("the InfoHub cell modem pulses hard and must not take the telemetry down.", 45, 62, 0, 0.8, B)

    silk("PORT A (U3) controller  IO17 DI / IO16 RO / IO4 DE+RE", 45, 72, 0, 0.8, B)
    silk("PORT B (U4) InfoHub     IO22 DI / IO23 RO / IO21 DE+RE", 45, 76, 0, 0.8, B)
    silk("JP1/JP2 = 120R termination. LEAVE OFF unless you see CRC errors:", 45, 81, 0, 0.8, B)
    silk("9600 baud proved reliable UNTERMINATED, 368/368 reads, 2026-08-31.", 45, 85, 0, 0.8, B)
    silk("ESP32-DevKitC-32, or -32U if you need an external antenna", 45, 89, 0, 0.8, B)

def gr_text(t,x,y,r,s,layer):
    return ['gr_text',q(t),['at',f"{x}",f"{y}",f"{r}"],['layer',q(layer)],['uuid',q(uid('gt',t,x,y,layer))],['effects',['font',['size',str(s),str(s)],['thickness',str(round(s*0.15,3))]],['justify','mirror'] if layer.startswith('B.') else ['justify']]]

def board_nets():
    N=nets(); names=sorted(N.keys(), key=lambda n:(netclass(n)!="GND",n))
    names+=sorted(unconnected_nets().values())
    return N,{n:i+1 for i,n in enumerate(names)}

def build(tracks=None, vias=None):
    N,netidx=board_nets()
    b=['kicad_pcb',['version','20241229'],['generator',q('bhydro_gen')],['generator_version',q('9.0')],['general',['thickness','1.6'],['legacy_teardrops','no']],['paper',q('A4')],
       ['title_block',['title',q('b-hydro carrier v2.1')],['date',q('2026-08-25')],['rev',q('2.1')]],
       ['layers',['0',q('F.Cu'),'signal'],['2',q('B.Cu'),'signal'],['9',q('F.Adhes'),'user',q('F.Adhesive')],['11',q('B.Adhes'),'user',q('B.Adhesive')],['13',q('F.Paste'),'user'],['15',q('B.Paste'),'user'],['5',q('F.SilkS'),'user',q('F.Silkscreen')],['7',q('B.SilkS'),'user',q('B.Silkscreen')],['1',q('F.Mask'),'user'],['3',q('B.Mask'),'user'],['17',q('Dwgs.User'),'user',q('User.Drawings')],['19',q('Cmts.User'),'user',q('User.Comments')],['21',q('Eco1.User'),'user',q('User.Eco1')],['23',q('Eco2.User'),'user',q('User.Eco2')],['25',q('Edge.Cuts'),'user'],['27',q('Margin'),'user'],['31',q('F.CrtYd'),'user',q('F.Courtyard')],['29',q('B.CrtYd'),'user',q('B.Courtyard')],['35',q('F.Fab'),'user'],['33',q('B.Fab'),'user']],
       ['setup',['pad_to_mask_clearance','0'],['allow_soldermask_bridges_in_footprints','no'],['tenting','front','back'],
         ['pcbplotparams',['layerselection','0x00000000_00000000_55555555_5755555f'],['plot_on_all_layers_selection','0x00000000_00000000_00000000_00000000'],['disableapertmacros','no'],['usegerberextensions','yes'],['usegerberattributes','yes'],['usegerberadvancedattributes','yes'],['creategerberjobfile','yes'],['dashed_line_dash_ratio','12.000000'],['dashed_line_gap_ratio','3.000000'],['svgprecision','4'],['plotframeref','no'],['mode','1'],['useauxorigin','no'],['hpglpennumber','1'],['hpglpenspeed','20'],['hpglpendiameter','15.000000'],['pdf_front_fp_property_popups','yes'],['pdf_back_fp_property_popups','yes'],['pdf_metadata','yes'],['pdf_single_document','no'],['dxfpolygonmode','yes'],['dxfimperialunits','yes'],['dxfusepcbnewfont','yes'],['psnegative','no'],['psa4output','no'],['plot_black_and_white','yes'],['sketchpadsonfab','no'],['plotpadnumbers','no'],['hidednponfab','no'],['sketchdnponfab','yes'],['crossoutdnponfab','yes'],['subtractmaskfromsilk','no'],['outputformat','1'],['mirror','no'],['drillshape','0'],['scaleselection','1'],['outputdirectory',q('gerbers/')]]]]
    b.append(['net','0',q('')])
    for n,i in sorted(netidx.items(), key=lambda x:x[1]): b.append(['net',str(i),q(n)])
    for ref in P: b.append(build_footprint(ref,netidx))
    # outline with 2 mm corner radius
    r=2.0
    def line(a,c): return ['gr_line',['start',f"{a[0]}",f"{a[1]}"],['end',f"{c[0]}",f"{c[1]}"],['stroke',['width','0.1'],['type','default']],['layer',q('Edge.Cuts')],['uuid',q(uid('edge',a,c))]]
    def arc(s,m,e): return ['gr_arc',['start',f"{s[0]:.4f}",f"{s[1]:.4f}"],['mid',f"{m[0]:.4f}",f"{m[1]:.4f}"],['end',f"{e[0]:.4f}",f"{e[1]:.4f}"],['stroke',['width','0.1'],['type','default']],['layer',q('Edge.Cuts')],['uuid',q(uid('edgearc',s,e))]]
    k=r*(1-math.sqrt(0.5))
    b+= [line((r,0),(BW-r,0)),line((BW,r),(BW,BH-r)),line((BW-r,BH),(r,BH)),line((0,BH-r),(0,r)),
         arc((BW-r,0),(BW-k,k),(BW,r)),arc((BW,BH-r),(BW-k,BH-k),(BW-r,BH)),arc((r,BH),(k,BH-k),(0,BH-r)),arc((0,r),(k,k),(r,0))]
    SILK.clear(); silkscreen()
    for t in SILK: b.append(gr_text(*t))
    # tracks / vias
    for t in (tracks or []):
        b.append(['segment',['start',f"{t[0]:.3f}",f"{t[1]:.3f}"],['end',f"{t[2]:.3f}",f"{t[3]:.3f}"],['width',f"{t[4]}"],['layer',q(t[5])],['net',str(netidx[t[6]])],['uuid',q(uid('seg',t))]])
    for v in (vias or []):
        b.append(['via',['at',f"{v[0]:.3f}",f"{v[1]:.3f}"],['size','0.8'],['drill','0.4'],['layers',q('F.Cu'),q('B.Cu')],['net',str(netidx[v[2]])],['uuid',q(uid('via',v))]])
    # GND zones both layers
    for lay in ("F.Cu","B.Cu"):
        b.append(['zone',['net',str(netidx["GND"])],['net_name',q('GND')],['layer',q(lay)],['uuid',q(uid('zone',lay))],['name',q('GND_'+lay[0])],['hatch','edge','0.5'],['priority','0'],
                  ['connect_pads',['clearance','0.3']],['min_thickness','0.25'],['filled_areas_thickness','no'],
                  ['fill','yes',['thermal_gap','0.4'],['thermal_bridge_width','0.5'],['island_removal_mode','0'],['island_area_min','10']],
                  ['polygon',['pts',['xy','0.5','0.5'],['xy',f"{BW-0.5}",'0.5'],['xy',f"{BW-0.5}",f"{BH-0.5}"],['xy','0.5',f"{BH-0.5}"]]]])
    # antenna keep-out under the module's antenna end (x 34..44 between the header rows)
    ax0,ax1,ay0,ay1=ESP_C[0]-27.5,ESP_C[0]-19.0,ESP_C[1]-11.2,ESP_C[1]+11.2
    b.append(['zone',['net','0'],['net_name',q('')],['layers',q('F&B.Cu')],['uuid',q(uid('keepout'))],['name',q('ANT_KEEPOUT')],['hatch','full','0.5'],
              ['keepout',['tracks','not_allowed'],['vias','not_allowed'],['pads','allowed'],['copperpour','not_allowed'],['footprints','allowed']],
              ['fill'],['polygon',['pts',['xy',f"{ax0}",f"{ay0}"],['xy',f"{ax1}",f"{ay0}"],['xy',f"{ax1}",f"{ay1}"],['xy',f"{ax0}",f"{ay1}"]]]])
    b.append(['embedded_fonts','no'])
    return b

def write_pro(path):
    classes=[{"name":"Default","clearance":0.25,"track_width":0.3,"via_diameter":0.8,"via_drill":0.4,"diff_pair_gap":0.25,"diff_pair_via_gap":0.25,"diff_pair_width":0.2,"microvia_diameter":0.3,"microvia_drill":0.1,"bus_width":12,"wire_width":6,"line_style":0,"pcb_color":"rgba(0, 0, 0, 0.000)","schematic_color":"rgba(0, 0, 0, 0.000)","priority":2147483647},
             {"name":"12V","clearance":0.25,"track_width":1.0,"via_diameter":0.8,"via_drill":0.4,"pcb_color":"rgba(255, 64, 64, 0.8)","schematic_color":"rgba(200, 0, 0, 1)","priority":0},
             {"name":"5V","clearance":0.25,"track_width":0.8,"via_diameter":0.8,"via_drill":0.4,"pcb_color":"rgba(255, 160, 0, 0.8)","schematic_color":"rgba(200,100,0,1)","priority":1},
             {"name":"GND","clearance":0.25,"track_width":0.5,"via_diameter":0.8,"via_drill":0.4,"pcb_color":"rgba(0, 160, 255, 0.8)","schematic_color":"rgba(0,80,200,1)","priority":2}]
    N=nets(); assign=[{"netclass":netclass(n),"pattern":n} for n in sorted(N) if netclass(n)!="Default"]
    pro={"board":{"3dviewports":[],"design_settings":{"defaults":{"board_outline_line_width":0.1,"copper_line_width":0.2,"silk_line_width":0.15,"silk_text_size_h":1.0,"silk_text_size_v":1.0,"silk_text_thickness":0.15},
          "rules":{"min_clearance":0.25,"min_connection":0.0,"min_copper_edge_clearance":0.3,"min_hole_clearance":0.25,"min_hole_to_hole":0.25,"min_microvia_diameter":0.2,"min_microvia_drill":0.1,"min_resolved_spokes":1,"min_silk_clearance":0.0,"min_text_height":0.6,"min_text_thickness":0.08,"min_through_hole_diameter":0.3,"min_track_width":0.2,"min_via_annular_width":0.15,"min_via_diameter":0.6,"solder_mask_to_copper_clearance":0.0,"use_height_for_length_calcs":True},
          "track_widths":[0.0,0.3,0.5,0.8,1.0],"via_dimensions":[{"diameter":0.0,"drill":0.0},{"diameter":0.8,"drill":0.4}]},"layer_presets":[],"viewports":[]},
         "boards":[],"cvpcb":{"equivalence_files":[]},"libraries":{"pinned_footprint_libs":[],"pinned_symbol_libs":[]},
         "meta":{"filename":PROJECT+".kicad_pro","version":3},
         "net_settings":{"classes":classes,"meta":{"version":4},"netclass_assignments":assign,"netclass_patterns":assign},
         "pcbnew":{"last_paths":{"gencad":"","idf":"","netlist":"","plot":"gerbers/","pos_files":"","specctra_dsn":"","step":"","svg":"","vrml":""},"page_layout_descr_file":""},
         "schematic":{"legacy_lib_dir":"","legacy_lib_list":[]},"sheets":[[ROOT_UUID,"Root"]],"text_variables":{}}
    json.dump(pro,open(path,'w'),indent=2)

if __name__=="__main__":
    import sys
    open("../"+PROJECT+".kicad_pcb","w").write(sexp.dump(build())+"\n"); write_pro("../"+PROJECT+".kicad_pro")
