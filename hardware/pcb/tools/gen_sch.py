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
    if lib=="binfohub": node=esp_symbol()
    else:
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

def esp_symbol():
    L=['symbol',q("ESP32-DevKitC-38"),['pin_names',['offset','1.016']],['exclude_from_sim','no'],['in_bom','yes'],['on_board','yes']]
    def prop(n,v,y,hide):
        e=['effects',['font',['size','1.27','1.27']]]
        if hide: e.append(['hide','yes'])
        return ['property',q(n),q(v),['at','0',str(y),'0'],e]
    L+= [prop("Reference","U",27.94,False),prop("Value","ESP32-DevKitC-38",-27.94,False),prop("Footprint","binfohub:ESP32-DevKitC-38",0,True),prop("Datasheet","https://docs.espressif.com/projects/esp-idf/en/latest/esp32/hw-reference/esp32/get-started-devkitc.html",0,True),
         prop("Description","ESP32-DevKitC V4 38-pin module (2x 1x19 2.54 mm rows, 25.4 mm apart)",0,True)]
    g=['symbol',q("ESP32-DevKitC-38_0_1"),['rectangle',['start','-12.7','25.4'],['end','12.7','-25.4'],['stroke',['width','0.254'],['type','default']],['fill',['type','background']]]]
    u=['symbol',q("ESP32-DevKitC-38_1_1")]
    for num,name,typ in ESP_PINS:
        i=(num-1)%19; y=22.86-2.54*i
        x,ang=(-17.78,0) if num<=19 else (17.78,180)
        u.append(['pin',typ,'line',['at',f"{x}",f"{y}",str(ang)],['length','5.08'],['name',q(name),['effects',['font',['size','1.27','1.27']]]],['number',q(str(num)),['effects',['font',['size','1.27','1.27']]]]])
    L+=[g,u]; return L

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
        """attach a power symbol (net in +5V/+3V3/+12V/GND) at point p with outward dir d"""
        s.n+=1
        if net=="GND": r={(0,1):0,(0,-1):180,(-1,0):270,(1,0):90}[d]
        else: r={(0,-1):0,(0,1):180,(-1,0):90,(1,0):270}[d]
        s.place(f"#PWR{s.n:03d}","power",net,net,"",p,r,ref_off=(0,0),val_off=(0,-3.0 if d==(0,-1) else 3.0))
    def flag(s,p,d):
        s.n+=1; r={(0,-1):0,(0,1):180,(-1,0):90,(1,0):270}[d]
        s.place(f"#FLG{s.n:03d}","power","PWR_FLAG","PWR_FLAG","",p,r,val_off=(0,-3.0))

POWER={"+5V","+3V3","+12V","GND"}
def hook(s,pins,netmap,ncs=(),stub_len=5.08):
    """for each pin: wire stub + label or power symbol"""
    for num,(cp,d) in pins.items():
        net=netmap.get(int(num)) if isinstance(list(netmap.keys())[0],int) else netmap.get(num)
        if net is None:
            if num in ncs or int(num) in ncs: s.nc(cp)
            continue
        e=s.stub(cp,d,stub_len)
        if net in POWER: s.power(net,e,d)
        else: s.label(net,e,d)

def place_part(s,ref,at,r=0,ncs=()):
    p=P[ref]; lib,name=SYM[p["sym"]]; fl,fn=FP[p["fp"]]
    pins=s.place(ref,lib,name,p["value"],fl+":"+fn,at,r,extra_props={"LCSC":p["lcsc"],"Description":p["desc"]},dnp=p["dnp"],ref_off=(2.54 if name!="ESP32-DevKitC-38" else 0,-1.27))
    hook(s,pins,p["pins"],ncs)

def build():
    s=Sch()
    # every ESP32 pin we do not use, marked no-connect so ERC stays clean
    NC=tuple(n for n,_,_ in ESP_PINS if n not in P["U1"]["pins"])

    s.text("B-INFOHUB BRIDGE v1.0  --  Briggs & Stratton GC-1032 RS-485 bridge with InfoHub passthrough",(20,14),2.5)

    # ---- power input ----
    s.text("POWER IN: 12 V from the generator harness. Q1 reverse-polarity (carries the InfoHub",(20,26))
    s.text("passthrough too, 4 A part). D2 TVS clamps starter load-dump. F2 fuses the InfoHub separately.",(20,30))
    place_part(s,"J1",(30,45),0); place_part(s,"Q1",(70,48),0)
    place_part(s,"R1",(92,52),0); place_part(s,"D1",(112,52),90)
    place_part(s,"D2",(134,52),90); place_part(s,"C1",(156,52),0); place_part(s,"C2",(174,52),0)
    place_part(s,"F2",(196,45),0)

    # ---- 5 V buck ----
    s.text("5 V RAIL: AP63205WU-7 sync buck, 3.8-32 V in, fixed 5 V 2 A (from b-hydro carrier v2.1)",(20,74))
    place_part(s,"U2",(70,96),0); place_part(s,"C3",(34,96),0); place_part(s,"R2",(34,124),0)
    place_part(s,"C4",(106,84),0); place_part(s,"L1",(112,104),0)
    place_part(s,"C5",(132,112),0); place_part(s,"C6",(152,112),0); place_part(s,"F1",(180,96),0)
    place_part(s,"C7",(200,112),0); place_part(s,"C8",(220,112),0)

    s.text("power flags",(20,140))
    # +12V_IH is a plain net (no stock power symbol) and +3V3 is driven by the
    # ESP32 module's power_out pin, so neither needs a flag here.
    for i,net in enumerate(["+12V","+5V","GND"]):
        pt=(round((26+i*30)/1.27)*1.27,round(150/1.27)*1.27); s.power(net,pt,(0,-1)); s.flag(pt,(0,1))

    # ---- RS-485 port A: controller ----
    s.text("PORT A -- GENERATOR CONTROLLER. We are Modbus MASTER here. Slave 10, 9600 8E1 (measured).",(20,166))
    s.text("RE and DE tied: one GPIO (IO4) drives direction. JP1 fits the 120R terminator.",(20,170))
    place_part(s,"J2",(30,186),0); place_part(s,"U3",(82,186),0); place_part(s,"C9",(126,204),0)
    place_part(s,"D3",(30,212),0); place_part(s,"R3",(126,176),0); place_part(s,"JP1",(150,176),0)

    # ---- RS-485 port B: InfoHub ----
    s.text("PORT B -- INFOHUB PASSTHROUGH. We are Modbus SERVER here, impersonating the controller",(20,232))
    s.text("at slave 10 so the InfoHub keeps working (ESPHome modbus role: server + modbus_server).",(20,236))
    place_part(s,"J3",(30,252),0); place_part(s,"U4",(82,252),0); place_part(s,"C10",(126,270),0)
    place_part(s,"D4",(30,278),0); place_part(s,"R4",(126,242),0); place_part(s,"JP2",(150,242),0)

    # ---- ESP32 ----
    s.text("ESP32-DevKitC-38, socketed. Use the -32U variant for an external antenna.",(232,26))
    s.text("No strapping pin (0/2/12/15) is used, so nothing here can stop it booting.",(232,30))
    place_part(s,"U1",(290,110),0,ncs=NC)

    # ---- status LEDs ----
    s.text("STATUS LEDS: PWR and TX need no GPIO -- TX is driven from DE, so it proves",(232,196))
    s.text("the bridge is actually transmitting, not merely powered.",(232,200))
    for i,(r,d) in enumerate([("R5","D5"),("R6","D6"),("R7","D7"),("R8","D8"),("R9","D9")]):
        x=250+i*34
        place_part(s,r,(x,214),0); place_part(s,d,(x,236),90)

    # ---- external LED header ----
    s.text("EXTERNAL LED HEADER: the on-board LEDs are invisible inside a sealed box.",(232,252))
    s.text("J4 carries the same anode nodes so panel LEDs can sit in parallel.",(232,256))
    place_part(s,"J4",(250,272),0)

    # ---- mounting ----
    s.text("mounting",(310,262),1.5)
    for i,h in enumerate(sorted(r for r in P if r.startswith("H"))):
        place_part(s,h,(318+i*15,272),0)
    return s

def write(path):
    s=build()
    root=['kicad_sch',['version','20250114'],['generator',q('binfohub_gen')],['generator_version',q('9.0')],['uuid',q(ROOT_UUID)],['paper',q('A3')],
          ['title_block',['title',q('B-Infohub Bridge v1.0')],['date',q('2026-08-31')],['rev',q('1.0')],['company',q('b-infohub')]]]
    ls=['lib_symbols']+list(s.libsyms.values()); root.append(ls)
    root+=s.items
    root.append(['sheet_instances',['path',q('/'),['page',q('1')]]])
    root.append(['embedded_fonts','no'])
    open(path,'w').write(sexp.dump(root)+"\n")
if __name__=="__main__":
    import sys; write(sys.argv[1] if len(sys.argv)>1 else "../binfohub_bridge.kicad_sch")
