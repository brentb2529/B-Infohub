"""Write project libraries: binfohub.kicad_sym (ESP32 symbol) and binfohub.pretty/ESP32-DevKitC-38.kicad_mod, plus lib tables."""
import sexp, os
from sexp import q
from gen_sch import esp_symbol
from circuit import ESP_PINS
def esp_footprint():
    fp=['footprint',q("ESP32-DevKitC-38"),['version','20241229'],['generator',q('bhydro_gen')],['layer',q('F.Cu')],
        ['descr',q("ESP32-DevKitC V4 38-pin module; two 1x19 2.54 mm rows 25.4 mm apart; USB-C toward +X")],['tags',q("ESP32 DevKitC module")],
        ['attr','through_hole']]
    def prop(n,v,y,hide,layer="F.Fab"):
        e=['effects',['font',['size','1','1'],['thickness','0.15']]]
        if hide: e.append(['hide','yes'])
        return ['property',q(n),q(v),['at','0',str(y),'0'],['layer',q(layer)],['uuid',q(sexp.q and __import__('circuit').uid('fpprop',n))],e]
    fp+= [prop("Reference","REF**",-15.5,False,"F.SilkS"),prop("Value","ESP32-DevKitC-38",15.5,False,"F.Fab"),prop("Datasheet","",0,True),prop("Description","",0,True)]
    L,W=55.0,28.0
    def rect(layer,hx,hy,w=0.12):
        return ['fp_rect',['start',f"{-hx}",f"{-hy}"],['end',f"{hx}",f"{hy}"],['stroke',['width',str(w)],['type','solid']],['fill','no'],['layer',q(layer)],['uuid',q(__import__('circuit').uid('fprect',layer))]]
    fp.append(rect("F.SilkS",L/2,W/2)); fp.append(rect("F.Fab",L/2,W/2,0.1)); fp.append(rect("F.CrtYd",L/2+0.5,W/2+0.5,0.05))
    # USB-C marker at +X end, antenna marker at -X end
    fp.append(['fp_text','user',q("USB-C >"),['at','22','0','0'],['layer',q('F.SilkS')],['uuid',q(__import__('circuit').uid('fpt1'))],['effects',['font',['size','1','1'],['thickness','0.15']]]])
    fp.append(['fp_text','user',q("ANT"),['at','-24','0','90'],['layer',q('F.SilkS')],['uuid',q(__import__('circuit').uid('fpt2'))],['effects',['font',['size','1','1'],['thickness','0.15']]]])
    fp.append(['fp_text','user',q("${REFERENCE}"),['at','0','0','0'],['layer',q('F.Fab')],['uuid',q(__import__('circuit').uid('fpt3'))],['effects',['font',['size','1','1'],['thickness','0.15']]]])
    for num,name,typ in ESP_PINS:
        i=(num-1)%19; x=-22.86+2.54*i; y=12.7 if num<=19 else -12.7
        shape='rect' if num in(1,20) else 'circle'
        fp.append(['pad',q(str(num)),'thru_hole',shape,['at',f"{x:.2f}",f"{y}"],['size','1.7','1.7'],['drill','1.0'],['layers',q('*.Cu'),q('*.Mask')],['remove_unused_layers','no'],['uuid',q(__import__('circuit').uid('fppad',num))]])
        fp.append(['fp_text','user',q(name.split('/')[0]),['at',f"{x:.2f}",f"{y+ (3.3 if num<=19 else -3.3)}",'90'],['layer',q('F.SilkS')],['uuid',q(__import__('circuit').uid('fpt',num))],['effects',['font',['size','0.7','0.7'],['thickness','0.1']]]])
    fp.append(['embedded_fonts','no'])
    return fp
def write(d):
    os.makedirs(d+"/binfohub.pretty",exist_ok=True)
    open(d+"/binfohub.pretty/ESP32-DevKitC-38.kicad_mod","w").write(sexp.dump(esp_footprint())+"\n")
    lib=['kicad_symbol_lib',['version','20241209'],['generator',q('bhydro_gen')],esp_symbol()]
    open(d+"/binfohub.kicad_sym","w").write(sexp.dump(lib)+"\n")
    open(d+"/sym-lib-table","w").write('(sym_lib_table\n  (version 7)\n  (lib (name "binfohub")(type "KiCad")(uri "${KIPRJMOD}/binfohub.kicad_sym")(options "")(descr "b-hydro project symbols"))\n)\n')
    open(d+"/fp-lib-table","w").write('(fp_lib_table\n  (version 7)\n  (lib (name "binfohub")(type "KiCad")(uri "${KIPRJMOD}/binfohub.pretty")(options "")(descr "b-hydro project footprints"))\n)\n')
if __name__=="__main__": write("..")
