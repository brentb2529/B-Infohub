"""b-infohub bridge v1.0 — single source of truth for parts, nets, placement.

Briggs & Stratton GC-1030/1031/1032 RS-485 bridge. Replaces the InfoHub as the
Modbus master while PASSING THE INFOHUB THROUGH on a second RS-485 port, so the
cell modem keeps working as an out-of-band backup.

Power section (input protection + AP63205 buck) is lifted from b-hydro carrier
v2.1, which is fab-proven and EE-reviewed. Do not "improve" it without reading
that project's README -- several values there are the result of a review that
caught real bugs.

Bus parameters were measured on the real controller 2026-08-31: slave 10,
9600 8E1. See ../../docs/field-findings-2026-08-31.md.
"""
import uuid
PROJECT="binfohub_bridge"
NS=uuid.UUID("7a2d3c4b-0000-4000-8000-00000000b1f0")
def uid(*k): return str(uuid.uuid5(NS,"|".join(map(str,k))))
ROOT_UUID=uid("root-sheet")

LIBS="/Applications/KiCad/KiCad.app/Contents/SharedSupport/"
FP={
 "R":("Resistor_SMD","R_0603_1608Metric"),
 "C":("Capacitor_SMD","C_0603_1608Metric"),
 "C0805":("Capacitor_SMD","C_0805_2012Metric"),
 "C1206":("Capacitor_SMD","C_1206_3216Metric"),
 "CPSMD":("Capacitor_SMD","CP_Elec_6.3x7.7"),
 "LED":("LED_SMD","LED_0603_1608Metric"),
 "SOT":("Package_TO_SOT_SMD","SOT-23"),
 "TSOT6":("Package_TO_SOT_SMD","TSOT-23-6"),
 "SOD":("Diode_SMD","D_SOD-123"),
 "SMB":("Diode_SMD","D_SMB"),
 "FUSE":("Fuse","Fuse_1812_4532Metric"),
 "L6045":("Inductor_SMD","L_Bourns_SRN6045TA"),
 "SOIC8":("Package_SO","SOIC-8_3.9x4.9mm_P1.27mm"),
 "PH2":("Connector_PinHeader_2.54mm","PinHeader_1x02_P2.54mm_Vertical"),
 "PH6":("Connector_PinHeader_2.54mm","PinHeader_1x06_P2.54mm_Vertical"),
 "PHX":("TerminalBlock_Phoenix","TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"),
 "XH2":("TerminalBlock_Phoenix","TerminalBlock_Phoenix_MPT-0,5-2-2.54_1x02_P2.54mm_Horizontal"),
 "XH3":("TerminalBlock_Phoenix","TerminalBlock_Phoenix_MPT-0,5-3-2.54_1x03_P2.54mm_Horizontal"),
 "XH4":("TerminalBlock_Phoenix","TerminalBlock_Phoenix_MPT-0,5-4-2.54_1x04_P2.54mm_Horizontal"),
 "MH":("MountingHole","MountingHole_3.2mm_M3"),
 "ESP":("binfohub","ESP32-DevKitC-38"),
}
SYM={
 "R":("Device","R"),"C":("Device","C"),"CP":("Device","C_Polarized"),
 "F":("Device","Polyfuse"),"LED":("Device","LED"),"L":("Device","L"),
 "PMOS":("Transistor_FET","AO3401A"),"DZ":("Device","D_Zener"),
 "TVS":("Device","D_TVS"),"TVS3":("Diode","SM712_SOT23"),
 "RS485":("Interface_UART","SP3485EN"),
 "BUCK":("Regulator_Switching","AP63205WU"),
 "J2":("Connector_Generic","Conn_01x02"),
 "J3":("Connector_Generic","Conn_01x03"),
 "J4":("Connector_Generic","Conn_01x04"),
 "J6":("Connector_Generic","Conn_01x06"),
 "MH":("Mechanical","MountingHole"),
 "ESP":("binfohub","ESP32-DevKitC-38"),
}

# ESP32-DevKitC V4 38-pin: 1-19 = 3V3 row (antenna end -> USB end), 20-38 = GND row
ESP_PINS=[(1,"3V3","power_out"),(2,"EN","input"),(3,"IO36/VP","input"),(4,"IO39/VN","input"),(5,"IO34","input"),(6,"IO35","input"),
 (7,"IO32","bidirectional"),(8,"IO33","bidirectional"),(9,"IO25","bidirectional"),(10,"IO26","bidirectional"),(11,"IO27","bidirectional"),
 (12,"IO14","bidirectional"),(13,"IO12","bidirectional"),(14,"GND","power_in"),(15,"IO13","bidirectional"),(16,"IO9/SD2","bidirectional"),
 (17,"IO10/SD3","bidirectional"),(18,"IO11/CMD","bidirectional"),(19,"5V","power_in"),
 (20,"GND","power_in"),(21,"IO23","bidirectional"),(22,"IO22","bidirectional"),(23,"IO1/TX0","bidirectional"),(24,"IO3/RX0","bidirectional"),
 (25,"IO21","bidirectional"),(26,"GND","power_in"),(27,"IO19","bidirectional"),(28,"IO18","bidirectional"),(29,"IO5","bidirectional"),
 (30,"IO17","bidirectional"),(31,"IO16","bidirectional"),(32,"IO4","bidirectional"),(33,"IO0","bidirectional"),(34,"IO2","bidirectional"),
 (35,"IO15","bidirectional"),(36,"IO8/SD1","bidirectional"),(37,"IO7/SD0","bidirectional"),(38,"IO6/CLK","bidirectional")]

P={}
def part(ref,sym,fp,value,pins,pcb,sch=None,lcsc="",desc="",dnp=False,hand=False,mpn=""):
    P[ref]=dict(sym=sym,fp=fp,value=value,pins=pins,pcb=pcb,sch=sch,lcsc=lcsc,desc=desc,dnp=dnp,hand=hand,mpn=mpn)

# ---------------- board ----------------
BW,BH=90.0,92.0
ESP_C=(45.0,55.0)          # module centre; pin rows at y = 42.3 / 67.7

# ===== ESP32 =====
# GPIO choice: every pin here is a plain I/O. No strapping pins (0/2/12/15) are
# used, so nothing on this board can stop the module booting.
#   IO17/IO16/IO4   -> port A transceiver (controller)   [matches validated firmware]
#   IO22/IO23/IO21  -> port B transceiver (InfoHub)
#   IO25/IO26/IO27  -> status LEDs
esp_nets={1:"+3V3",9:"LED_WIFI",10:"LED_BUS",11:"LED_FAULT",14:"GND",19:"+5V",20:"GND",
 21:"B_RO",22:"B_DI",25:"B_DE",26:"GND",30:"A_DI",31:"A_RO",32:"A_DE"}
part("U1","ESP","ESP","ESP32-DevKitC-32 (38-pin)",esp_nets,(ESP_C[0],ESP_C[1],0),
     desc="ESP32-DevKitC V4 38-pin; plugs into 2x 1x19 female headers",hand=True,mpn="ESP32-DevKitC-32")

# ===== power input =====
part("J1","J2","PHX","12V IN",{1:"12V_IN",2:"GND"},(12.0,7.0,0),lcsc="C474881",
     desc="Screw terminal 5.08 2P: +12 V (harness red/grey) and GND (harness black)",hand=True)
part("Q1","PMOS","SOT","AO3401A",{1:"Q1_G",2:"+12V",3:"12V_IN"},(10.0,18.0,0),lcsc="C15127",
     desc="P-MOSFET reverse-polarity protection, 4 A -- carries BOTH our load and the InfoHub passthrough")
part("R1","R","R","4k7",{1:"Q1_G",2:"GND"},(16.0,18.0,90),lcsc="C23162",
     desc="Q1 gate pull-down; ~0.4 mA through D1 keeps the clamp in its characterised region")
part("D1","DZ","SOD","BZT52C10",{1:"+12V",2:"Q1_G"},(21.0,18.0,90),lcsc="C173431",
     desc="10 V zener gate-source: clamps Q1 Vgs within the AO3401A +-12 V limit")
part("D2","TVS","SMB","SMBJ16A",{1:"+12V",2:"GND"},(26.5,18.0,90),lcsc="C353386",
     desc="Input TVS. b-hydro skipped this on purpose (indoor). A generator pad is not indoor: "
          "the starter is a large inductive load. 16 V standoff clears the 14.6 V charging rail.")
part("C1","CP","CPSMD","100uF 25V",{1:"+12V",2:"GND"},(35.5,18.0,0),lcsc="C3338",
     desc="12 V bulk: holds the rail through the crank dip (11.4 V measured 2026-08-31)")
part("C2","C","C","100nF 50V",{1:"+12V",2:"GND"},(41.0,18.0,90),lcsc="C14663",desc="12 V HF decoupling")

# ===== InfoHub 12 V passthrough =====
# Separately fused. The InfoHub's cell modem pulses hard on transmit; sharing a
# fuse with the bridge would let an InfoHub fault take out the telemetry -- the
# exact opposite of the point of this box.
part("F2","F","FUSE","2A polyfuse 1812",{1:"+12V",2:"+12V_IH"},(45.5,33.0,0),lcsc="C2760293",
     desc="SMD1812-200C-30V, 2 A hold / 4 A trip, 30 V: InfoHub supply, independent of F1")

# ===== 5 V buck (AP63205WU-7) -- lifted from b-hydro carrier v2.1 =====
part("U2","BUCK","TSOT6","AP63205WU-7",{1:"5V_BUCK",2:"BUCK_EN",3:"+12V",4:"GND",5:"BUCK_SW",6:"BUCK_BST"},
     (14.0,28.0,0),lcsc="C2071056",desc="Sync buck 3.8-32 V in, fixed 5 V 2 A, TSOT-23-6")
part("C3","C","C1206","10uF 50V",{1:"+12V",2:"GND"},(14.0,33.5,0),lcsc="C13585",desc="buck input cap, right at VIN. 50 V not 25 V: ceramics lose a lot of capacitance under DC bias, and this sits on a 14.6 V rail. (b-hydro used C89632; that part is down to single-digit stock at LCSC, so this board takes the basic-part equivalent.)")
part("R2","R","R","100k",{1:"+12V",2:"BUCK_EN"},(7.5,28.0,90),lcsc="C25803",desc="buck EN pull-up (always on)")
part("C4","C","C","100nF 50V",{1:"BUCK_BST",2:"BUCK_SW"},(19.0,26.0,90),lcsc="C14663",desc="bootstrap cap BST-SW")
part("L1","L","L6045","10uH 2.5A",{1:"BUCK_SW",2:"5V_BUCK"},(25.0,32.0,0),lcsc="C79272",desc="SWPA6045S100MT shielded 6x6")
part("C5","C","C0805","22uF 25V",{1:"5V_BUCK",2:"GND"},(31.0,32.0,90),lcsc="C45783",desc="buck output cap 1")
part("C6","C","C0805","22uF 25V",{1:"5V_BUCK",2:"GND"},(34.0,32.0,90),lcsc="C45783",desc="buck output cap 2")
part("F1","F","FUSE","1.1A polyfuse",{1:"5V_BUCK",2:"+5V"},(32.0,26.5,0),lcsc="C883148",
     desc="1.1 A hold / 2.2 A trip on the 5 V rail, below the buck's 3.2 A limit")
part("C7","C","C0805","22uF 25V",{1:"+5V",2:"GND"},(40.0,32.0,90),lcsc="C45783",desc="5 V bulk near the ESP 5V pin")
part("C8","C","C","100nF 50V",{1:"+5V",2:"GND"},(43.0,26.5,90),lcsc="C14663",desc="5 V HF decoupling")

# ===== RS-485 port A: the generator controller (we are MASTER) =====
part("J2","J2","XH2","BUS A B",{1:"BUS_A",2:"BUS_B"},(50.0,7.0,0),lcsc="C474920",
     desc="Screw terminal 2.54 2P to the ABC controller: A and B only. The harness ground "
          "arrives on J1 and is the same net, so a separate ground pin here would be "
          "redundant. Swap A/B if the bus stays silent.",hand=True)
part("U3","RS485","SOIC8","SP3485EN",{1:"A_RO",2:"A_DE",3:"A_DE",4:"A_DI",5:"GND",6:"BUS_A",7:"BUS_B",8:"+3V3"},
     (52.0,27.0,0),lcsc="C8963",desc="3.3 V half-duplex RS-485, controller side. RE and DE tied: one GPIO drives direction.")
part("C9","C","C","100nF 50V",{1:"+3V3",2:"GND"},(58.5,32.0,90),lcsc="C14663",desc="U3 decoupling")
part("D3","TVS3","SOT","SM712",{1:"BUS_A",2:"BUS_B",3:"GND"},(50.0,20.5,0),lcsc="C32677",
     desc="PSM712 RS-485 TVS on the controller pair (asymmetric -7/+12 V, the RS-485 standard part)")
part("R3","R","R","120R",{1:"BUS_A",2:"TERM_A"},(58.5,20.5,0),lcsc="C22787",desc="bus termination, controller side")
part("JP1","J2","PH2","TERM 120R",{1:"TERM_A",2:"BUS_B"},(62.5,20.5,0),lcsc="C492401",
     desc="120R termination jumper, controller side. LEAVE OPEN by default: 368 consecutive error-free block reads at 9600 8E1 on 2026-08-31 with an unterminated adapter, and at 104 us per bit reflections settle ~1000x faster than the sampling instant. Fit only if CRC errors appear.",hand=True)

# ===== RS-485 port B: the InfoHub (we are SERVER, impersonating the controller) =====
part("J3","J4","XH4","IH 12V GND A B",{1:"+12V_IH",2:"GND",3:"IH_A",4:"IH_B"},(70.0,7.0,0),lcsc="C474922",
     desc="Screw terminal 2.54 4P to the InfoHub: +12 V (fused by F2), GND, A, B",hand=True)
part("U4","RS485","SOIC8","SP3485EN",{1:"B_RO",2:"B_DE",3:"B_DE",4:"B_DI",5:"GND",6:"IH_A",7:"IH_B",8:"+3V3"},
     (72.0,27.0,0),lcsc="C8963",desc="3.3 V half-duplex RS-485, InfoHub side. ESPHome modbus role: server.")
part("C10","C","C","100nF 50V",{1:"+3V3",2:"GND"},(78.5,32.0,90),lcsc="C14663",desc="U4 decoupling")
part("D4","TVS3","SOT","SM712",{1:"IH_A",2:"IH_B",3:"GND"},(70.0,20.5,0),lcsc="C32677",desc="PSM712 RS-485 TVS on the InfoHub pair")
part("R4","R","R","120R",{1:"IH_A",2:"TERM_B"},(78.5,20.5,0),lcsc="C22787",desc="bus termination, InfoHub side")
part("JP2","J2","PH2","TERM 120R",{1:"TERM_B",2:"IH_B"},(82.5,20.5,0),lcsc="C492401",
     desc="120R termination jumper, InfoHub side. LEAVE OPEN by default -- same reasoning as JP1.",hand=True)

# ===== status LEDs =====
# Answers 'what is this box doing?' without a laptop. PWR and TX need no GPIO.
# LED row. These coordinates drive the light-pipe holes in the enclosure lid --
# change them here and regenerate the box, never the other way round.
LEDY, LEDRY = 80.0, 75.0
LEDX0, LEDPITCH = 18.0, 11.0
_leds=[("D5","GREEN","C965804","R5","+5V","LED_PWR","power: the 5 V rail is up"),
       ("D6","BLUE","C965807","R6","LED_WIFI","LED_WIFI_A","Wi-Fi associated"),
       ("D7","GREEN","C965804","R7","LED_BUS","LED_BUS_A","Modbus online: the controller is answering"),
       ("D8","RED","C2286","R8","LED_FAULT","LED_FLT_A","a generator fault is active"),
       ("D9","YELLOW","C965803","R9","A_DE","LED_TX_A","transmit: driven from DE, so it needs no GPIO "
                                                       "and proves the bridge is actually talking")]
# LED drive current is set for LIGHT PIPES, not for looking at a bare board.
# A 3.3 V GPIO minus a blue/green Vf of ~2.9 V leaves only ~0.4 V, so the series
# resistor has to be small or the LED is invisible through a pipe:
#     blue/green  100R -> ~4 mA        red/yellow  330R -> ~4 mA
#     PWR (green, from the 5 V rail)   330R -> ~6 mA
# 1k would have given the blue LED ~0.5 mA. Fine on a bench, useless in a box.
for i,(dref,col,dlcsc,rref,src,anode,why) in enumerate(_leds):
    x=LEDX0+i*LEDPITCH
    hi_vf = col in ("BLUE","GREEN") and src != "+5V"
    rval,rlcsc = ("100R","C22775") if hi_vf else ("330R","C23138")
    part(rref,"R","R",rval,{1:src,2:anode},(x,LEDRY,0),lcsc=rlcsc,
         desc=(f"{dref} series resistor, ~4 mA."
               + (" Small value: blue/green Vf leaves little headroom on 3.3 V." if hi_vf else "")))
    part(dref,"LED","LED",col,{1:"GND",2:anode},(x,LEDY,0),lcsc=dlcsc,
         desc=f"{col} LED -- {why}. Sits under a light pipe in the lid; see enclosure docs.")

# ===== external LED header =====
# The indicators are read through light pipes in the lid, so this header is a spare
# route for a remote panel: wire external LEDs cathode to pin 1 and they sit in
# parallel with the on-board ones, sharing their series resistors.
part("J4","J6","PH6","LED OUT",{1:"GND",2:"LED_PWR",3:"LED_WIFI_A",4:"LED_BUS_A",
     5:"LED_FLT_A",6:"LED_TX_A"},(85.0,54.0,0),lcsc="C492405",
     desc="External LED header: GND, PWR, WIFI, BUS, FAULT, TX",hand=True)

# ===== mounting holes =====
for i,(x,y) in enumerate([(4.5,4.5),(85.5,4.5),(4.5,87.5),(85.5,87.5),(4.5,46.0),(85.5,46.0)]):
    part(f"H{i+1}","MH","MH","M3",{},(x,y,0),desc="M3 mounting hole")

# ---------------- nets / classes ----------------
def nets():
    N={}
    for ref,p in P.items():
        for pad,net in p["pins"].items(): N.setdefault(net,[]).append((ref,str(pad)))
    return N
def netclass(net):
    if net in("+12V","12V_IN","+12V_IH"): return "12V"
    if net in("+5V","5V_BUCK","BUCK_SW"): return "5V"
    if net=="GND": return "GND"
    if net in("BUS_A","BUS_B","IH_A","IH_B","TERM_A","TERM_B"): return "RS485"
    return "Default"
WIDTH={"12V":1.0,"5V":0.8,"GND":0.5,"RS485":0.4,"Default":0.3}

def unconnected_nets():
    out={}
    for num,name,typ in ESP_PINS:
        if num not in P["U1"]["pins"]:
            out[num]="unconnected-(U1-%s-Pad%d)"%(name.replace('/','{slash}'),num)
    return out

# hand-routed segments the grid router cannot escape (TSOT-23-6 buck pins)
PRE=[
 # U3 SOIC-8 @ (52,27): pins 1-4 exit left, 5-8 exit right
 (49.525,26.365,48.0,26.365,0.25,"F.Cu","A_DE"),
 (49.525,27.635,48.0,27.635,0.25,"F.Cu","A_DE"),
 (48.0,26.365,48.0,27.635,0.25,"F.Cu","A_DE"),      # RE and DE are one net: link them
 (54.475,27.635,56.6,27.635,0.3,"F.Cu","BUS_A"),
 (54.475,26.365,56.6,26.365,0.3,"F.Cu","BUS_B"),
 # U4 SOIC-8 @ (72,27)
 (69.525,26.365,67.5,26.365,0.25,"F.Cu","B_DE"),
 (69.525,27.635,67.5,27.635,0.25,"F.Cu","B_DE"),
 (67.5,26.365,67.5,27.635,0.25,"F.Cu","B_DE"),
 (74.475,27.635,76.6,27.635,0.3,"F.Cu","IH_A"),
 (74.475,26.365,76.6,26.365,0.3,"F.Cu","IH_B"),
 # U2 TSOT-23-6 @ (14,28)
 (12.863,28.0,10.8,28.0,0.25,"F.Cu","BUCK_EN"),
 (15.137,27.05,17.4,26.2,0.25,"F.Cu","BUCK_BST"),
]

# ---------------- terminal-block orientation fix ----------------
# Carried over from b-hydro: KiCad's *_Horizontal terminal footprints put the wire
# openings on the +y side of the pad row, i.e. facing INTO the board at rot 0. JLC's
# DFM review flagged this on that project. Rotate each block 180 deg about its own pad
# row so the openings face the board edge; holes stay put and the pad->net map reverses.
import math as _m
_TERM_PITCH={"PHX":5.08,"XH2":2.54,"XH3":2.54,"XH4":2.54}
for _ref,_p in P.items():
    if _p["fp"] not in _TERM_PITCH: continue
    _n=len(_p["pins"]); _d=(_n-1)*_TERM_PITCH[_p["fp"]]
    _x,_y,_r=_p["pcb"]; _a=_m.radians(_r)
    _p["pcb"]=(round(_x+_d*_m.cos(_a),4), round(_y-_d*_m.sin(_a),4), (_r+180)%360)
    _p["pins"]={_n+1-k:v for k,v in _p["pins"].items()}
