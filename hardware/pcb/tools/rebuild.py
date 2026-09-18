"""Rebuild the board file from circuit.py + saved routes.pkl (after silk/text-only edits)."""
import pickle, sexp, gen_pcb
from circuit import PROJECT
tracks,vias=pickle.load(open("routes.pkl","rb"))
open("../"+PROJECT+".kicad_pcb","w").write(sexp.dump(gen_pcb.build(tracks,vias))+"\n"); gen_pcb.write_pro("../"+PROJECT+".kicad_pro")
print("rebuilt with",len(tracks),"tracks",len(vias),"vias")
