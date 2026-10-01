"""Generate binfohub_bridge.kicad_sch from circuit.py (label-based, grouped by function)."""
import math, copy, sexp
from circuit import *
from sexp import q

SYMDIR=LIBS+"symbols/"
libcache={}
def get_lib_symbol(lib,name):
    """Return flattened lib symbol node renamed to Lib:Name, plus pin list [(num,name,type,x,y,ang,len)]"""
    key=(lib,name)
    if key in libcache: return libcache[key]
    node=sexp.load_symbol(SYMDIR+lib+".kicad_sym",name)
    ext=sexp.find1(node,'extends')
    if ext:
        parent=get_lib_symbol(lib,sexp.unq(ext[1]))[0]
        parent=copy.deepcopy(parent); pname=sexp.unq(parent[1]).split(':')[1]
        props={sexp.unq(p[1]):p for p in sexp.find(node,'property')}
        new=['symbol',q(name)]
        for c in parent[2:]:
            if isinstance(c,list) and c[0]=='property':
                if sexp.unq(c[1]) in props: c=props.pop(sexp.unq(c[1]))
            if isinstance(c,list) and c[0]=='symbol':
                c[1]=q(sexp.unq(c[1]).replace(pname+'_',name+'_',1))
            new.append(c)
        for p in props.values(): new.append(p)
        node=new
    node=copy.deepcopy(node); node[1]=q(lib+":"+name)
    pins=[]
    for u in sexp.find(node,'symbol'):
        for p in sexp.find(u,'pin'):
            at=sexp.find1(p,'at')
            pins.append((sexp.unq(sexp.find1(p,'number')[1]),sexp.unq(sexp.find1(p,'name')[1]),p[1],float(at[1]),float(at[2]),float(at[3]),float(sexp.find1(p,'length')[1])))
    libcache[key]=(node,pins); return libcache[key]

def pin_key(num):
    """Pad number to look a symbol pin up by in the part's pin->net map.

    KiCad 10 writes a stack of identically-named pins as ONE pin numbered
    "[1,15,38,39]" (the WROOM's four GND pads). The first member stands for
    the stack; circuit.py lists every member in the map, so any would do.
    """
    s=str(num)
    if s.startswith('['): s=s[1:].split(',')[0]
    return int(s) if s.isdigit() else s

def rot(px,py,r):
    c=math.cos(math.radians(r)); s=math.sin(math.radians(r)); return (px*c-py*s, px*s+py*c)

class Sch:
    def __init__(s): s.items=[]; s.libsyms={}; s.n=0
    def add(s,x): s.items.append(x)
    def wire(s,a,b): s.add(['wire',['pts',['xy',f"{a[0]:.4f}",f"{a[1]:.4f}"],['xy',f"{b[0]:.4f}",f"{b[1]:.4f}"]],['stroke',['width','0'],['type','default']],['uuid',q(uid('w',len(s.items),a,b))]])
    def label(s,name,p,dirv):
        ang={(1,0):0,(-1,0):180,(0,-1):90,(0,1):270}[dirv]
        just={0:'left',180:'right',90:'left',270:'right'}[ang]
        s.add(['global_label',q(name),['shape','passive'],['at',f"{p[0]:.4f}",f"{p[1]:.4f}",str(ang)],['fields_autoplaced','yes'],['effects',['font',['size','1.27','1.27']],['justify',just]],['uuid',q(uid('l',len(s.items),name,p))],
               ['property',q('Intersheetrefs'),q('${INTERSHEET_REFS}'),['at',f"{p[0]:.4f}",f"{p[1]:.4f}",'0'],['effects',['font',['size','1.27','1.27']],['hide','yes']]]])
    def text(s,txt,p,size=2.0):
        s.add(['text',q(txt),['exclude_from_sim','no'],['at',f"{p[0]}",f"{p[1]}",'0'],['effects',['font',['size',str(size),str(size)],['bold','yes']],['justify','left','bottom']],['uuid',q(uid('t',txt,p))]])
    def nc(s,p): s.add(['no_connect',['at',f"{p[0]:.4f}",f"{p[1]:.4f}"],['uuid',q(uid('nc',p))]])
    def place(s,ref,lib,name,value,fp,at,r=0,props=None,extra_props=None,dnp=False,ref_off=(0,0),val_off=None):
        node,pins=get_lib_symbol(lib,name); s.libsyms[lib+":"+name]=node
        X,Y=(round(at[0]/1.27)*1.27, round(at[1]/1.27)*1.27); su=uid('sym',ref)
        sym=['symbol',['lib_id',q(lib+":"+name)],['at',f"{X}",f"{Y}",str(r)],['unit','1'],['exclude_from_sim','no'],['in_bom','yes' if not (ref.startswith('#') or ref.startswith('H')) else 'no'],['on_board','yes'],['dnp','yes' if dnp else 'no'],['uuid',q(su)]]
        def prop(n,v,off,hide):
            e=['effects',['font',['size','1.27','1.27']]]
            if hide: e.append(['hide','yes'])
            return ['property',q(n),q(v),['at',f"{X+off[0]:.4f}",f"{Y+off[1]:.4f}",'0'],e]
        hidden_ref = ref.startswith('#')
        sym.append(prop("Reference",ref,ref_off,hidden_ref))
        sym.append(prop("Value",value,val_off if val_off else (ref_off[0],ref_off[1]+2.54),hidden_ref and name!='PWR_FLAG' and False))
        sym.append(prop("Footprint",fp,(0,0),True)); sym.append(prop("Datasheet","~",(0,0),True))
        for k,v in (extra_props or {}).items(): sym.append(prop(k,v,(0,0),True))
        for p in pins: sym.append(['pin',q(p[0]),['uuid',q(uid('pin',ref,p[0]))]])
        sym.append(['instances',['project',q(PROJECT),['path',q('/'+ROOT_UUID),['reference',q(ref)],['unit','1']]]])
        s.add(sym)
        out={}
        for num,pname,typ,px,py,pang,plen in pins:
            rx,ry=rot(px,py,r); cp=(X+rx,Y-ry)
            ox,oy=rot(math.cos(math.radians(pang+180)),math.sin(math.radians(pang+180)),r); d=(round(ox),round(-oy))
            out[num]=(cp,d)
        return out
    def stub(s,cp,d,length=2.54):
        e=(cp[0]+d[0]*length,cp[1]+d[1]*length); s.wire(cp,e); return e
    def power(s,net,p,d):
        """attach a power symbol (net in +3V3/+12V/GND) at point p with outward dir d"""
        s.n+=1
        if net=="GND": r={(0,1):0,(0,-1):180,(-1,0):270,(1,0):90}[d]
        else: r={(0,-1):0,(0,1):180,(-1,0):90,(1,0):270}[d]
        s.place(f"#PWR{s.n:03d}","power",net,net,"",p,r,ref_off=(0,0),val_off=(0,-3.0 if d==(0,-1) else 3.0))
    def flag(s,p,d):
        s.n+=1; r={(0,-1):0,(0,1):180,(-1,0):90,(1,0):270}[d]
        s.place(f"#FLG{s.n:03d}","power","PWR_FLAG","PWR_FLAG","",p,r,val_off=(0,-3.0))

POWER={"+3V3","+12V","GND"}
def hook(s,pins,netmap,ncs=(),stub_len=5.08):
    """for each pin: wire stub + label or power symbol"""
    for num,(cp,d) in pins.items():
        k=pin_key(num)
        net=netmap.get(k)
        if net is None:
            if k in ncs: s.nc(cp)
            continue
        e=s.stub(cp,d,stub_len)
        if net in POWER: s.power(net,e,d)
        else: s.label(net,e,d)

def place_part(s,ref,at,r=0,ncs=()):
    p=P[ref]; lib,name=SYM[p["sym"]]; fl,fn=FP[p["fp"]]
    pins=s.place(ref,lib,name,p["value"],fl+":"+fn,at,r,extra_props={"LCSC":p["lcsc"],"Description":p["desc"]},dnp=p["dnp"],ref_off=(2.54,-1.27))
    hook(s,pins,p["pins"],ncs)

def build():
    s=Sch()
    # every module pin we do not use is marked no-connect so ERC stays clean
    # (the symbol's own NC-type pins included -- a flag on those is harmless)
    NC=tuple(n for n,_,_ in ESP_PINS if n not in P["U1"]["pins"])

    s.text(f"B-INFOHUB BRIDGE v{REV}  --  Briggs & Stratton GC-1032 RS-485 bridge with InfoHub passthrough",(20,14),2.5)

    # ---- power input ----
    s.text("POWER IN: 12 V from the generator harness. Q1 reverse-polarity (carries the InfoHub",(20,26))
    s.text("passthrough too, 4 A part). D2 TVS clamps starter load-dump. F2 fuses the InfoHub separately.",(20,30))
    place_part(s,"J1",(30,45),0); place_part(s,"Q1",(70,48),0)
    place_part(s,"R1",(92,52),0); place_part(s,"D1",(112,52),90)
    place_part(s,"D2",(134,52),90); place_part(s,"C1",(156,52),0); place_part(s,"C2",(174,52),0)
    place_part(s,"F2",(196,45),0)

    # ---- 3.3 V buck ----
    s.text("3.3 V RAIL: AP63203WU-7 sync buck, 3.8-32 V in, fixed 3.3 V 2 A (circuit from b-hydro carrier v2.1).",(20,74))
    s.text("Rev 1.1: one rail. The 5 V rail only fed the DevKit's linear 3.3 V regulator, which is gone.",(20,78))
    place_part(s,"U2",(70,96),0); place_part(s,"C3",(34,96),0); place_part(s,"R2",(34,124),0)
    place_part(s,"C4",(106,84),0); place_part(s,"L1",(112,104),0)
    place_part(s,"C5",(132,112),0); place_part(s,"C6",(152,112),0); place_part(s,"F1",(180,96),0)

    s.text("power flags",(20,140))
    # +12V_IH / FAN_12V are plain nets (no stock power symbol). +3V3 comes off an
    # inductor, so it has no power_out pin of its own and needs a flag.
    for i,net in enumerate(["+12V","+3V3","GND"]):
        pt=(round((26+i*30)/1.27)*1.27,round(150/1.27)*1.27); s.power(net,pt,(0,-1)); s.flag(pt,(0,1))

    # ---- RS-485 port A: controller ----
    s.text("PORT A -- GENERATOR CONTROLLER. We are Modbus MASTER here. Slave 10, 9600 8E1 (measured).",(20,166))
    s.text("RE and DE tied: one GPIO (IO4) drives direction. JP1 fits the 120R terminator.",(20,170))
    place_part(s,"J2",(30,186),0); place_part(s,"U3",(82,186),0); place_part(s,"C9",(126,204),0)
    place_part(s,"D3",(30,212),0); place_part(s,"R3",(126,176),0); place_part(s,"JP1",(150,176),0)
    place_part(s,"R16",(176,204),90)

    # ---- RS-485 port B: InfoHub ----
    s.text("PORT B -- INFOHUB PASSTHROUGH. We are Modbus SERVER here, impersonating the controller",(20,232))
    s.text("at slave 10 so the InfoHub keeps working. R10/R11 bias the idle pair (rev 1.1).",(20,236))
    place_part(s,"J3",(30,252),0); place_part(s,"U4",(82,252),0); place_part(s,"C10",(126,270),0)
    place_part(s,"D4",(30,278),0); place_part(s,"R4",(126,242),0); place_part(s,"JP2",(150,242),0)
    place_part(s,"R10",(176,242),90); place_part(s,"R11",(176,270),90)
    place_part(s,"R17",(198,270),90)

    # ---- mounting ----
    s.text("mounting",(20,288),1.5)
    for i,h in enumerate(sorted(r for r in P if r.startswith("H"))):
        place_part(s,h,(40+i*15,292),0)

    # ---- ESP32 ----
    s.text("ESP32-WROOM-32E soldered (rev 1.1; was a socketed DevKitC). Same pads take the -32UE",(232,26))
    s.text("for a U.FL remote antenna. No strapping pin carries a function; IO0 is BOOT only.",(232,30))
    place_part(s,"U1",(290,100),0,ncs=NC)

    # ---- ESP support ----
    s.text("EN/BOOT: 10k pull-ups, 1 uF on EN. SW1 RESET, SW2 BOOT (diagonal pads only -- see circuit.py).",(232,152))
    s.text("J6 PROG: 3V3 GND TX RX EN IO0 -- first flash with any 3.3 V USB-serial adapter, OTA after that.",(232,156))
    place_part(s,"R14",(250,168),0); place_part(s,"C11",(272,168),0); place_part(s,"SW1",(292,168),0)
    place_part(s,"R15",(318,168),0); place_part(s,"SW2",(340,168),0)
    place_part(s,"J6",(372,100),0)
    place_part(s,"C7",(372,160),0); place_part(s,"C8",(392,160),0)

    # ---- status LEDs ----
    s.text("STATUS LEDS: PWR and TX need no GPIO -- TX is driven from DE, so it proves",(232,196))
    s.text("the bridge is actually transmitting, not merely powered. All on 3.3 V, 100R blue/green.",(232,200))
    for i,(r,d) in enumerate([("R5","D5"),("R6","D6"),("R7","D7"),("R8","D8"),("R9","D9")]):
        x=250+i*34
        place_part(s,r,(x,214),0); place_part(s,d,(x,236),90)

    # ---- external LED header + fan ----
    s.text("J4 EXT LED: the same anode nodes, for panel LEDs in parallel.  FAN (rev 1.1): 12 V via F3,",(232,252))
    s.text("Q2 low-side PWM from IO32, D10 flyback, R13 holds the fan OFF while the ESP is in reset.",(232,256))
    place_part(s,"J4",(250,272),0)
    place_part(s,"J5",(290,272),0); place_part(s,"F3",(314,264),0); place_part(s,"D10",(334,272),90)
    place_part(s,"Q2",(360,278),0); place_part(s,"R12",(382,268),0); place_part(s,"R13",(382,284),90)
    return s

def write(path):
    s=build()
    root=['kicad_sch',['version','20250114'],['generator',q('binfohub_gen')],['generator_version',q('9.0')],['uuid',q(ROOT_UUID)],['paper',q('A3')],
          ['title_block',['title',q(f'B-Infohub Bridge v{REV}')],['date',q('2026-10-01')],['rev',q(REV)],['company',q('b-infohub')]]]
    ls=['lib_symbols']+list(s.libsyms.values()); root.append(ls)
    root+=s.items
    root.append(['sheet_instances',['path',q('/'),['page',q('1')]]])
    root.append(['embedded_fonts','no'])
    open(path,'w').write(sexp.dump(root)+"\n")
if __name__=="__main__":
    import sys; write(sys.argv[1] if len(sys.argv)>1 else "../binfohub_bridge.kicad_sch")
