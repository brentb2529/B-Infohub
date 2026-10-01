"""b-infohub bridge v1.1 — single source of truth for parts, nets, placement.

Briggs & Stratton GC-1030/1031/1032 RS-485 bridge. Replaces the InfoHub as the
Modbus master while PASSING THE INFOHUB THROUGH on a second RS-485 port, so the
cell modem keeps working as an out-of-band backup.

Power section (input protection + AP6320x buck) is lifted from b-hydro carrier
v2.1, which is fab-proven and EE-reviewed. Do not "improve" it without reading
that project's README -- several values there are the result of a review that
caught real bugs. Rev 1.1 changes only the buck's fixed output (5 V -> 3.3 V,
same family, same pinout, same application circuit).

Bus parameters were measured on the real controller 2026-08-31: slave 10,
9600 8E1. See ../../docs/field-findings-2026-08-31.md.

REV 1.1 -- what changed and why (each has its own section below):
  * ESP32-WROOM-32E module soldered to the board, replacing the socketed
    DevKitC. Measured on the fielded rev 1.0 unit, 2026-10-01: die 125-135 F
    at night (~75 F of self-heating in the box), 188 F in afternoon sun, and
    at 188 F the RS-485 link to the controller dropped a byte per reply. The
    DevKit's AMS1117 LDO (5 -> 3.3 V linear, ~0.3 W inside the module
    footprint) is gone; the module sits on a via-stitched ground pad.
  * 3.3 V single rail from an AP63203 buck. The 5 V rail only ever fed the
    DevKit's LDO and the PWR LED. One efficient stage, 12 V -> 3.3 V.
  * Same footprint takes the -32UE (U.FL) for a remote antenna; the antenna
    end faces the board edge so the enclosure wall is the only thing in front
    of it. Order -32E for the stock internal antenna, -32UE + a U.FL-to-SMA
    bulkhead pigtail when the box is metal or the signal is poor.
  * Fan header (J5): 12 V, PWM-switched by an N-MOSFET from IO32, fused,
    flyback-protected. Firmware drives it from the die temperature; see
    packages/fan.yaml. Fit a fan only if shading the enclosure is not enough.
  * EN/IO0 support (pull-ups, EN RC, RESET and BOOT buttons) and a 6-pin
    programming header (J6) for the one USB-serial flash a bare module needs.
    After that it is OTA, as before.
  * R10/R11 fail-safe bias on the InfoHub pair (carried from the rev 1.1
    source-only change of 2026-09-28).
Enclosure interface is unchanged: outline, mounting holes, terminal positions
on the top edge and the LED light-pipe row are exactly rev 1.0.
"""
import uuid
PROJECT="binfohub_bridge"
REV="1.1"
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
 "SMA":("Diode_SMD","D_SMA"),
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
 # Project footprints (gen_libs.py writes them): the stock KiCad WROOM-32E
 # footprint with its antenna courtyard/keepout narrowed to +-12 mm (see the
 # ESP32 section), and the XKB TS-1187A 5.1 mm tactile switch.
 "ESPW":("binfohub","ESP32-WROOM-32E_edge"),
 "SW4":("binfohub","SW_TS-1187A"),
}
SYM={
 "R":("Device","R"),"C":("Device","C"),"CP":("Device","C_Polarized"),
 "F":("Device","Polyfuse"),"LED":("Device","LED"),"L":("Device","L"),
 "PMOS":("Transistor_FET","AO3401A"),"NMOS":("Transistor_FET","AO3400A"),
 "DZ":("Device","D_Zener"),"DS":("Device","D_Schottky"),
 "TVS":("Device","D_TVS"),"TVS3":("Diode","SM712_SOT23"),
 "RS485":("Interface_UART","SP3485EN"),
 "BUCK":("Regulator_Switching","AP63203WU"),
 "SW":("Switch","SW_Push"),
 "J2":("Connector_Generic","Conn_01x02"),
 "J3":("Connector_Generic","Conn_01x03"),
 "J4":("Connector_Generic","Conn_01x04"),
 "J6":("Connector_Generic","Conn_01x06"),
 "MH":("Mechanical","MountingHole"),
 "ESPW":("RF_Module","ESP32-WROOM-32E"),
}

# ESP32-WROOM-32E, KiCad RF_Module symbol / footprint numbering. The four GND
# pins are one stacked symbol pin numbered "[1,15,38,39]"; it is listed here
# once, under 1, and gen_sch/gen_pcb map the stack back to its pads. Pad 39 is
# the exposed thermal pad -- the footprint carries its own via array.
ESP_PINS=[(1,"GND","power_in"),(2,"VDD","power_in"),(3,"EN","input"),
 (4,"SENSOR_VP","input"),(5,"SENSOR_VN","input"),(6,"IO34","input"),(7,"IO35","input"),
 (8,"IO32","bidirectional"),(9,"IO33","bidirectional"),(10,"IO25","bidirectional"),
 (11,"IO26","bidirectional"),(12,"IO27","bidirectional"),(13,"IO14","bidirectional"),
 (14,"IO12","bidirectional"),(15,"GND","power_in"),(16,"IO13","bidirectional"),
 (17,"NC","no_connect"),(18,"NC","no_connect"),(19,"NC","no_connect"),(20,"NC","no_connect"),
 (21,"NC","no_connect"),(22,"NC","no_connect"),(23,"IO15","bidirectional"),
 (24,"IO2","bidirectional"),(25,"IO0","bidirectional"),(26,"IO4","bidirectional"),
 (27,"IO16","bidirectional"),(28,"IO17","bidirectional"),(29,"IO5","bidirectional"),
 (30,"IO18","bidirectional"),(31,"IO19","bidirectional"),(32,"NC","no_connect"),
 (33,"IO21","bidirectional"),(34,"RXD0/IO3","bidirectional"),(35,"TXD0/IO1","bidirectional"),
 (36,"IO22","bidirectional"),(37,"IO23","bidirectional"),(38,"GND","power_in"),(39,"GND","power_in")]
ESP_GND_STACK="[1,15,38,39]"

P={}
def part(ref,sym,fp,value,pins,pcb,sch=None,lcsc="",desc="",dnp=False,hand=False,mpn=""):
    P[ref]=dict(sym=sym,fp=fp,value=value,pins=pins,pcb=pcb,sch=sch,lcsc=lcsc,desc=desc,dnp=dnp,hand=hand,mpn=mpn)

# ---------------- board ----------------
BW,BH=90.0,92.0

# ===== ESP32 =====
# GPIO choice: every pin here is a plain I/O. No strapping pin (0/2/12/15) is
# used for a function, so nothing on this board can stop the module booting.
# IO0 is the BOOT input only: pulled up, and pulled low by SW2 or J6 pin 6.
#   IO17/IO16/IO4   -> port A transceiver (controller)   [matches validated firmware]
#   IO22/IO23/IO21  -> port B transceiver (InfoHub)
#   IO25/IO26/IO27  -> status LEDs
#   IO32            -> fan PWM (Q2 gate)
#   TXD0/RXD0       -> programming header J6 only
#
# PLACEMENT. The module sits at the RIGHT board edge, antenna end facing the
# edge: KiCad's footprint carries Espressif's antenna keepout as a courtyard
# and a copper keepout, and the only place on this board where that region can
# be empty is off the edge. The enclosure-fixed features (terminals on the top
# edge, LED light pipes along y = 80, six mounting holes) rule out every other
# orientation. The stock keepout is +-24 mm wide across the antenna; the
# project copy narrows it to +-12 mm so it clears the mounting hole at
# (85.5, 46) -- that is still 3 mm beyond the module body each side, and the
# region in front of the antenna is kept bare out to the board edge
# (12 mm). The hole's screw head is 14 mm off the antenna axis.
#
# Footprint rotation 270: local -y (antenna) -> board +x. Pads 1-14 run along
# y = 53.25, pads 25-38 along y = 70.75, pads 15-24 at x = 53.5.
ESP_C=(66.0,62.0); ESP_ROT=270
ANT_KEEPOUT=(72.56, BW, 50.0, 74.0)   # board-space rectangle, both copper layers; the router honours it
esp_nets={1:"GND",15:"GND",38:"GND",39:"GND",
 2:"+3V3",3:"ESP_EN",8:"FAN_PWM",10:"LED_WIFI",11:"LED_BUS",12:"LED_FAULT",
 25:"ESP_IO0",26:"A_DE",27:"A_RO",28:"A_DI",33:"B_DE",34:"ESP_RXD0",35:"ESP_TXD0",36:"B_DI",37:"B_RO"}
part("U1","ESPW","ESPW","ESP32-WROOM-32E",esp_nets,(ESP_C[0],ESP_C[1],ESP_ROT),lcsc="C2973652",
     desc="ESP32-WROOM-32E, 4 MB. Soldered module, antenna toward the board edge. "
          "ALTERNATE: ESP32-WROOM-32UE-N4 (C2934568) -- identical pads, U.FL instead of the PCB antenna; "
          "fit with a U.FL-to-SMA bulkhead pigtail through the enclosure for a remote antenna. Rev 1.1.")

# Module supply decoupling: the module datasheet asks for >=10 uF close to VDD
# (pad 2, at board (70.0, 53.25)) plus a 100 nF. Wi-Fi transmit bursts pull
# ~300 mA peaks through here; the buck's two 22 uF are 40 mm away.
part("C7","C","C0805","10uF 25V",{1:"+3V3",2:"GND"},(69.0,49.0,0),lcsc="C15850",desc="3.3 V bulk at the module VDD pad")
part("C8","C","C","100nF 50V",{1:"+3V3",2:"GND"},(72.5,46.5,0),lcsc="C14663",desc="3.3 V HF decoupling at the module")

# EN: pull-up plus an RC so power-up reset is clean -- the DevKit had exactly
# this (10k + 1 uF) and the module datasheet asks for it. SW1 pulls EN low for
# a hardware reset. 1 uF, not 100 nF: the slower rise is deliberate, it keeps
# the chip in reset until the 3.3 V rail is well established.
part("R14","R","R","10k",{1:"+3V3",2:"ESP_EN"},(65.0,49.0,0),lcsc="C25804",desc="EN pull-up")
part("C11","C","C","1uF 50V",{1:"ESP_EN",2:"GND"},(61.0,49.0,0),lcsc="C15849",desc="EN reset RC (10k/1uF ~ 10 ms)")
# BOOT: IO0 low at reset selects the serial bootloader. Pulled up; SW2 or J6
# pin 6 pulls it low. Only ever needed for the first flash.
part("R15","R","R","10k",{1:"+3V3",2:"ESP_IO0"},(47.0,71.5,0),lcsc="C25804",desc="IO0 (BOOT) pull-up")
# The TS-1187A is a 4-pad switch whose pads are paired per side internally.
# Only the two DIAGONAL pads carry a net (footprint pads 1 and 2; 3 and 4 are
# unassigned), so the switch works whichever way the maker pairs them and can
# never be a permanent short -- a shorted EN would be a board that never boots.
# Both carry the same VALUE on purpose: the BOM groups by value, and two lines
# for one LCSC part is what JLC's review flags and deselects. RESET/BOOT are silk.
part("SW1","SW","SW4","TS-1187A",{1:"ESP_EN",2:"GND"},(57.0,42.0,0),lcsc="C318884",
     desc="RESET: pulls EN low. XKB TS-1187A-B-A-B 5.1 mm tactile, JLC basic part")
part("SW2","SW","SW4","TS-1187A",{1:"ESP_IO0",2:"GND"},(69.0,42.0,0),lcsc="C318884",
     desc="BOOT: hold while pressing RESET to enter the serial bootloader")
# Programming header. The DevKit's USB bridge is gone; this is how the first
# image gets on. Any 3.3 V USB-serial adapter: wire GND/TX/RX, hold BOOT,
# tap RESET, `esphome run`. Pin 1 (3V3) is for adapters that need a reference,
# not for powering the board -- feed 12 V on J1 as normal.
# On the left edge beside J4: reachable with the lid off, clear of the back-silk
# text block (J6 is through-hole, so its pads are on the back too) and out of
# the signal corridor between the module and the LED row.
part("J6","J6","PH6","PROG",{1:"+3V3",2:"GND",3:"ESP_TXD0",4:"ESP_RXD0",5:"ESP_EN",6:"ESP_IO0"},(14.0,50.0,0),lcsc="C492405",
     desc="Programming header: 3V3, GND, TX0, RX0, EN, IO0. First flash only; OTA after that.",hand=True)

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
part("F2","F","FUSE","2A polyfuse 1812",{1:"+12V",2:"+12V_IH"},(45.5,33.5,0),lcsc="C2760293",
     desc="SMD1812-200C-30V, 2 A hold / 4 A trip, 30 V: InfoHub supply, independent of F1")

# ===== 3.3 V buck (AP63203WU-7) -- application circuit from b-hydro carrier v2.1 =====
# Rev 1.0 made 5 V here (AP63205) and let the DevKit's AMS1117 drop it to 3.3 V
# linearly. Nothing on this board needs 5 V, so rev 1.1 makes 3.3 V directly:
# same part family, same pinout, same inductor and capacitors -- the AP6320x
# datasheet's 10 uH / 2x22 uF circuit covers every fixed-output member.
part("U2","BUCK","TSOT6","AP63203WU-7",{1:"3V3_BUCK",2:"BUCK_EN",3:"+12V",4:"GND",5:"BUCK_SW",6:"BUCK_BST"},
     (14.0,28.0,0),lcsc="C780769",desc="Sync buck 3.8-32 V in, fixed 3.3 V 2 A, TSOT-23-6. Rev 1.1: was AP63205 (5 V).")
part("C3","C","C1206","10uF 50V",{1:"+12V",2:"GND"},(14.0,33.5,0),lcsc="C13585",desc="buck input cap, right at VIN. 50 V not 25 V: ceramics lose a lot of capacitance under DC bias, and this sits on a 14.6 V rail. (b-hydro used C89632; that part is down to single-digit stock at LCSC, so this board takes the basic-part equivalent.)")
part("R2","R","R","100k",{1:"+12V",2:"BUCK_EN"},(7.5,28.0,90),lcsc="C25803",desc="buck EN pull-up (always on)")
part("C4","C","C","100nF 50V",{1:"BUCK_BST",2:"BUCK_SW"},(19.0,26.0,90),lcsc="C14663",desc="bootstrap cap BST-SW")
part("L1","L","L6045","10uH 2.5A",{1:"BUCK_SW",2:"3V3_BUCK"},(25.0,32.0,0),lcsc="C79272",desc="SWPA6045S100MT shielded 6x6")
part("C5","C","C0805","22uF 25V",{1:"3V3_BUCK",2:"GND"},(31.0,32.0,90),lcsc="C45783",desc="buck output cap 1")
part("C6","C","C0805","22uF 25V",{1:"3V3_BUCK",2:"GND"},(34.0,32.0,90),lcsc="C45783",desc="buck output cap 2")
part("F1","F","FUSE","1.1A polyfuse",{1:"3V3_BUCK",2:"+3V3"},(32.0,26.5,0),lcsc="C883148",
     desc="1.1 A hold / 2.2 A trip on the 3.3 V rail, below the buck's 3.2 A limit")

# ===== fan output (J5) =====
# 12 V, low-side switched by Q2 from IO32 at 25 kHz PWM, so a plain 2-wire fan
# gets a controllable average voltage and a 4-wire fan can be run from its
# supply pins alone. 0.5 A polyfuse (F3): a stalled 12 V fan is a heater, and
# this rail also carries the InfoHub. D10 catches the motor's inductive kick
# when Q2 opens; without it the drain sees a spike every PWM cycle.
# Q2 is the AO3400A: 48 mohm at 2.5 V gate drive, so a 3.3 V GPIO turns it on
# fully. R12 slows the gate edge a little (EMI); R13 holds the fan OFF while the
# ESP is in reset or being flashed -- an undriven gate must not mean a running fan.
part("J5","J2","XH2","FAN 12V",{1:"FAN_12V",2:"FAN_SW"},(28.0,42.0,0),lcsc="C474920",
     desc="Fan header, screw terminal 2.54 2P: +12 V (fused by F3) and switched return. 2-wire 12 V fan, 0.5 A max. Rev 1.1.",hand=True)
part("F3","F","FUSE","0.5A polyfuse 1812",{1:"+12V",2:"FAN_12V"},(37.5,42.0,0),lcsc="C462518",
     desc="SMD1812P050TF/60: 0.5 A hold / 1 A trip. Fan supply, independent of F1/F2")
part("D10","DS","SMA","SS14",{1:"FAN_12V",2:"FAN_SW"},(37.5,47.5,0),lcsc="C2480",
     desc="Flyback across the fan: cathode to +12 V, anode to the switched node")
part("Q2","NMOS","SOT","AO3400A",{1:"FAN_G",2:"GND",3:"FAN_SW"},(29.0,51.0,0),lcsc="C20917",
     desc="N-MOSFET low-side fan switch, 5.7 A, logic-level gate")
part("R12","R","R","100R",{1:"FAN_PWM",2:"FAN_G"},(23.0,51.0,0),lcsc="C22775",desc="Q2 gate series resistor")
part("R13","R","R","10k",{1:"FAN_G",2:"GND"},(23.0,55.0,0),lcsc="C25804",desc="Q2 gate pull-down: fan off while the ESP is in reset")

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
part("C10","C","C","100nF 50V",{1:"+3V3",2:"GND"},(64.5,33.0,90),lcsc="C14663",desc="U4 decoupling")
part("D4","TVS3","SOT","SM712",{1:"IH_A",2:"IH_B",3:"GND"},(70.0,20.5,0),lcsc="C32677",desc="PSM712 RS-485 TVS on the InfoHub pair")
part("R4","R","R","120R",{1:"IH_A",2:"TERM_B"},(78.5,20.5,0),lcsc="C22787",desc="bus termination, InfoHub side")
part("JP2","J2","PH2","TERM 120R",{1:"TERM_B",2:"IH_B"},(82.5,20.5,0),lcsc="C492401",
     desc="120R termination jumper, InfoHub side. LEAVE OPEN by default -- same reasoning as JP1.",hand=True)

# ---- fail-safe bias on the InfoHub pair ----------------------------------
# Port B is a bus WE create, with two devices and nothing holding it at a known
# level between frames. The SP3485 only guarantees a defined receiver output
# for OPEN inputs; an idle, connected pair is not open, so when our driver
# releases the line A-B floats inside the +/-200 mV dead band and the receiver
# flickers on noise. Measured 2026-09-28 with raw frame logging: 35-57 ms
# after every 175-byte reply, ~61 bytes of garbage (0xFA.., 0xFF..) arrive on
# port B; ESPHome's server treats them as an incoming request, defers its next
# reply and then drops it -- 8 of 36 replies to the InfoHub in 75 s, and the
# InfoHub re-asking after 0.8 s each time. Port A never shows this: the
# GC-1032 biases its own bus.
#
# A pull-up on A and a pull-down on B hold the idle pair at a definite "1".
# With JP2 OPEN (the default, and correct for a cable of a metre or two) the
# only load is the two receivers' ~12k inputs, so 4k7 gives ~1.3 V idle
# differential -- six times the dead band. IF TERMINATION IS EVER FITTED the
# 120R dominates and these must drop to 560R-680R to stay above 200 mV; the
# 4k7 pair is then too weak. Fitted by default: this is a fix, not an option.
part("R10","R","R","4k7",{1:"+3V3",2:"IH_A"},(66.0,25.0,90),lcsc="C23162",
     desc="Fail-safe bias, InfoHub pair: pull-up on A. 4k7 with JP2 open; 680R if JP2 is fitted. Rev 1.1.")
part("R11","R","R","4k7",{1:"IH_B",2:"GND"},(66.0,29.0,90),lcsc="C23162",
     desc="Fail-safe bias, InfoHub pair: pull-down on B. 4k7 with JP2 open; 680R if JP2 is fitted. Rev 1.1.")

# ===== status LEDs =====
# Answers 'what is this box doing?' without a laptop. PWR and TX need no GPIO.
# LED row. These coordinates drive the light-pipe holes in the enclosure lid --
# change them here and regenerate the box, never the other way round. The LEDs
# are at y = 80 exactly as rev 1.0; only the resistor row moved (75 -> 77.5)
# to clear the module's bottom pad row at y = 70.75.
LEDY, LEDRY = 80.0, 77.5
LEDX0, LEDPITCH = 18.0, 11.0
_leds=[("D5","GREEN","C965804","R5","+3V3","LED_PWR","power: the 3.3 V rail is up"),
       ("D6","BLUE","C965807","R6","LED_WIFI","LED_WIFI_A","Wi-Fi associated"),
       ("D7","GREEN","C965804","R7","LED_BUS","LED_BUS_A","Modbus online: the controller is answering"),
       ("D8","RED","C2286","R8","LED_FAULT","LED_FLT_A","a generator fault is active"),
       ("D9","YELLOW","C965803","R9","A_DE","LED_TX_A","transmit: driven from DE, so it needs no GPIO "
                                                       "and proves the bridge is actually talking")]
# LED drive current is set for LIGHT PIPES, not for looking at a bare board.
# 3.3 V minus a blue/green Vf of ~2.9 V leaves only ~0.4 V, so the series
# resistor has to be small or the LED is invisible through a pipe:
#     blue/green  100R -> ~4 mA        red/yellow  330R -> ~4 mA
# 1k would have given the blue LED ~0.5 mA. Fine on a bench, useless in a box.
# Rev 1.1: PWR is now on 3.3 V like the others, so it takes 100R too (was 330R
# from 5 V). Firmware dims the GPIO-driven three by PWM; PWR and TX are fixed.
for i,(dref,col,dlcsc,rref,src,anode,why) in enumerate(_leds):
    x=LEDX0+i*LEDPITCH
    hi_vf = col in ("BLUE","GREEN")
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
# Rev 1.1: moved from the right edge (now the antenna's clear zone) to the left.
part("J4","J6","PH6","LED OUT",{1:"GND",2:"LED_PWR",3:"LED_WIFI_A",4:"LED_BUS_A",
     5:"LED_FLT_A",6:"LED_TX_A"},(8.0,54.0,0),lcsc="C492405",
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
    if net in("+12V","12V_IN","+12V_IH","FAN_12V","FAN_SW"): return "12V"
    if net in("+3V3","3V3_BUCK","BUCK_SW"): return "3V3"
    if net=="GND": return "GND"
    if net in("BUS_A","BUS_B","IH_A","IH_B","TERM_A","TERM_B"): return "RS485"
    return "Default"
WIDTH={"12V":1.0,"3V3":0.8,"GND":0.5,"RS485":0.4,"Default":0.3}

def unconnected_nets():
    out={}
    for num,name,typ in ESP_PINS:
        if num not in P["U1"]["pins"]:
            out[num]="unconnected-(U1-%s-Pad%d)"%(name.replace('/','{slash}'),num)
    return out

# hand-routed segments the grid router cannot escape (TSOT-23-6 buck pins)
PRE=[
 # U3 SOIC-8 @ (52,27): pins 1-4 exit left, 5-8 exit right; the corner pins
 # (1, 4, 5, 8) exit along the body instead, out of the row, rev 1.1.
 (49.525,26.365,48.0,26.365,0.25,"F.Cu","A_DE"),
 (49.525,27.635,48.0,27.635,0.25,"F.Cu","A_DE"),
 (48.0,26.365,48.0,27.635,0.25,"F.Cu","A_DE"),      # RE and DE are one net: link them
 (49.525,25.095,49.525,23.6,0.25,"F.Cu","A_RO"),
 (49.525,28.905,49.525,30.6,0.25,"F.Cu","A_DI"),
 (54.475,27.635,56.6,27.635,0.3,"F.Cu","BUS_A"),
 (54.475,26.365,56.6,26.365,0.3,"F.Cu","BUS_B"),
 (54.475,25.095,54.475,23.6,0.25,"F.Cu","+3V3"),
 (54.475,28.905,54.475,30.6,0.25,"F.Cu","GND"),
 # U4 SOIC-8 @ (72,27)
 (69.525,26.365,67.5,26.365,0.25,"F.Cu","B_DE"),
 (69.525,27.635,67.5,27.635,0.25,"F.Cu","B_DE"),
 (67.5,26.365,67.5,27.635,0.25,"F.Cu","B_DE"),
 (69.525,25.095,69.525,23.6,0.25,"F.Cu","B_RO"),    # rev 1.1: pin 1 escapes upward, R10 now sits to its left
 (69.525,28.905,69.525,30.6,0.25,"F.Cu","B_DI"),
 (74.475,27.635,76.6,27.635,0.3,"F.Cu","IH_A"),
 (74.475,26.365,76.6,26.365,0.3,"F.Cu","IH_B"),
 (74.475,25.095,74.475,23.6,0.25,"F.Cu","+3V3"),
 (74.475,28.905,74.475,30.6,0.25,"F.Cu","GND"),
 # U2 TSOT-23-6 @ (14,28)
 (12.863,28.0,10.8,28.0,0.25,"F.Cu","BUCK_EN"),
 (15.137,27.05,17.4,26.2,0.25,"F.Cu","BUCK_BST"),
 # rev 1.1: SW and GND hand-routed all the way. The 12 V class routes first
 # and its 1 mm feed to F2/F3 cut the corridor between U2 and L1 on every pass.
 (15.137,28.0,17.6,28.0,0.25,"F.Cu","BUCK_SW"),
 (17.6,28.0,20.6,31.0,0.6,"F.Cu","BUCK_SW"),
 (20.6,31.0,22.925,32.0,0.6,"F.Cu","BUCK_SW"),       # L1 pad 1
 (15.137,28.95,17.4,29.8,0.25,"F.Cu","GND"),
 (17.4,29.8,17.4,31.6,0.5,"F.Cu","GND"),
 (17.4,31.6,15.475,33.5,0.5,"F.Cu","GND"),           # C3 pad 2
 # U1 WROOM @ (66,62) rot 270: VDD (pad 2) sits between GND and EN at 1.27 mm
 # pitch and is fully inside their clearance. Straight out of the row to C7.
 (69.99,53.25,69.99,50.6,0.4,"F.Cu","+3V3"),
 (69.99,50.6,68.05,50.6,0.4,"F.Cu","+3V3"),
 (68.05,50.6,68.05,49.0,0.4,"F.Cu","+3V3"),          # C7 pad 1
 # C7's GND pad is boxed in by that track below and the module's escape traffic;
 # GND routes last. Straight up, then to SW2's GND pad (the diagonal pair's pad 2).
 (69.95,49.0,69.95,46.0,0.5,"F.Cu","GND"),
 (69.95,46.0,72.25,43.85,0.5,"F.Cu","GND"),          # SW2 pad 2
]
# Every other used module pad gets a straight escape stub out of its row, for
# the same reason: at 1.27 mm pitch the pad interiors sit inside the neighbours'
# clearance and A* has nowhere to start. Top row (pads 1-14) exits -y, bottom
# row (25-38) exits +y. Pad n of the top row is at x = 71.26 - (n-1)*1.27; pad
# n of the bottom row at x = 54.75 + (n-25)*1.27.
for _n,_net in ((3,"ESP_EN"),(8,"FAN_PWM"),(10,"LED_WIFI"),(11,"LED_BUS"),(12,"LED_FAULT")):
    _x=round(71.26-(_n-1)*1.27,3); PRE.append((_x,53.25,_x,51.4,0.3,"F.Cu",_net))
for _n,_net in ((25,"ESP_IO0"),(26,"A_DE"),(27,"A_RO"),(28,"A_DI"),(33,"B_DE"),(34,"ESP_RXD0"),(35,"ESP_TXD0"),(36,"B_DI"),(37,"B_RO")):
    _x=round(54.75+(_n-25)*1.27,3); PRE.append((_x,70.75,_x,72.6,0.3,"F.Cu",_net))

# ---------------- terminal-block orientation fix ----------------
# Carried over from b-hydro: KiCad's *_Horizontal terminal footprints put the wire
# openings on the +y side of the pad row, i.e. facing INTO the board at rot 0. JLC's
# DFM review flagged this on that project. Rotate each block 180 deg about its own pad
# row so the openings face the board edge; holes stay put and the pad->net map reverses.
# J5 (fan) is an interior block; the same pass leaves its openings facing -y,
# toward the terminal edge, which is where a fan lead naturally comes from.
import math as _m
_TERM_PITCH={"PHX":5.08,"XH2":2.54,"XH3":2.54,"XH4":2.54}
for _ref,_p in P.items():
    if _p["fp"] not in _TERM_PITCH: continue
    _n=len(_p["pins"]); _d=(_n-1)*_TERM_PITCH[_p["fp"]]
    _x,_y,_r=_p["pcb"]; _a=_m.radians(_r)
    _p["pcb"]=(round(_x+_d*_m.cos(_a),4), round(_y-_d*_m.sin(_a),4), (_r+180)%360)
    _p["pins"]={_n+1-k:v for k,v in _p["pins"].items()}
