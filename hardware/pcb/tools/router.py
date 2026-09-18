"""Grid A* router (2 layers + vias) for the b-hydro carrier. 0.25 mm grid."""
import math, heapq, numpy as np
from scipy import ndimage
from circuit import *
import gen_pcb

G=0.25; NX=int(BW/G)+1; NY=int(BH/G)+1
CLR=0.25; EDGE=0.35; VIA_D=0.8
def cells(x,y): return (int(round(x/G)),int(round(y/G)))

class Router:
    def __init__(s):
        s.N,s.netidx=gen_pcb.board_nets()
        s.cu={"F":np.zeros((NX,NY),np.int16),"B":np.zeros((NX,NY),np.int16)}   # net index of copper; -1 = keepout
        s.padcells={}   # (ref,pad) -> [(layer,ix,iy)] interior cells
        s.tracks=[]; s.vias=[]; s.prelinks={}
        s.pads=[]
        for ref in P: s.pads+=gen_pcb.pad_geoms(ref)
        # keepouts: mounting bosses (r 5 mm) on both layers, board edge band, antenna region
        X,Y=np.meshgrid(np.arange(NX)*G,np.arange(NY)*G,indexing='ij')
        for lay in "FB":
            m=s.cu[lay]
            # take the hole positions from circuit.py rather than hard-coding them --
            # these were still b-hydro's 120x90 corners, so two of the four keepouts
            # sat off this board entirely and two of our real holes had none.
            for (hx,hy) in [(P[h]["pcb"][0],P[h]["pcb"][1]) for h in P if h.startswith("H")]:
                m[(X-hx)**2+(Y-hy)**2 < 4.6**2]=-1
            m[(X<EDGE)|(X>BW-EDGE)|(Y<EDGE)|(Y>BH-EDGE)]=-1
            ax0,ax1,ay0,ay1=ESP_C[0]-27.5,ESP_C[0]-19.0,ESP_C[1]-11.2,ESP_C[1]+11.2
            m[(X>=ax0)&(X<=ax1)&(Y>=ay0)&(Y<=ay1)]=-1
        s.X,s.Y=X,Y
        for pd in s.pads: s.raster_pad(pd)
        for (x1,y1,x2,y2,w,lay,net) in PRE: s.pre_track(x1,y1,x2,y2,w,lay,net)
    def raster_pad(s,pd):
        idx=s.netidx[pd["net"]] if pd["net"] else -1
        a=math.radians(pd["rot"]); c=math.cos(a); sn=math.sin(a)
        dx=s.X-pd["x"]; dy=s.Y-pd["y"]
        lx=dx*c-dy*sn; ly=dx*sn+dy*c     # to pad-local (approx sign irrelevant for symmetric shapes)
        w,h=pd["w"],pd["h"]
        if pd["shape"]=="circle": inside=(dx**2+dy**2)<=(w/2+0.13)**2; inner=(dx**2+dy**2)<=max(w/2-0.2,0.05)**2
        else:
            inside=(np.abs(lx)<=w/2+0.13)&(np.abs(ly)<=h/2+0.13); inner=(np.abs(lx)<=max(w/2-0.2,0.05))&(np.abs(ly)<=max(h/2-0.2,0.05))
        if pd["tht"] and pd["drill"]>0:
            inner=inner&((dx**2+dy**2)>(pd["drill"]/2+0.1)**2) if False else inner
        layers="FB" if pd["tht"] else "F"
        for lay in layers:
            m=s.cu[lay]; m[inside&(m==0)]=idx if idx>0 else -1
            if idx>0:
                if pd["tht"] and pd["drill"]>0: pass
                s.padcells.setdefault((pd["ref"],pd["pad"]),[]).extend([(lay,int(i),int(j)) for i,j in zip(*np.nonzero(inner))])
    def pre_track(s,x1,y1,x2,y2,w,lay,net):
        idx=s.netidx[net]; n=int(math.hypot(x2-x1,y2-y1)/(G/2))+1; cells=set()
        for k in range(n+1):
            t=k/n; x=x1+(x2-x1)*t; y=y1+(y2-y1)*t
            i,j=int(round(x/G)),int(round(y/G)); s.mark_disk(lay[0],i,j,w/2,idx)
            cells.add((lay[0],i,j))
        s.tracks.append((x1,y1,x2,y2,w,lay,net))
        ends=[]
        for (ex,ey) in ((x1,y1),(x2,y2)):
            hit=[p for p in s.pads if p["net"]==net and math.hypot(p["x"]-ex,p["y"]-ey)<0.3]
            ends.append((hit[0]["ref"],hit[0]["pad"]) if hit else None)
        for a,b in ((ends[0],ends[1]),(ends[1],ends[0])):
            if a: s.prelinks.setdefault(a,[]).append((cells,b))
    def obstacles(s,idx,w):
        """dilated obstacle maps for net idx with track width w, plus via-ok map"""
        r=(w/2+CLR+0.08)/G+0.5; rv=(VIA_D/2+CLR+0.08)/G+0.5
        out={}; vok=np.ones((NX,NY),bool)
        for lay in "FB":
            other=(s.cu[lay]!=0)&(s.cu[lay]!=idx)
            d=ndimage.distance_transform_edt(~other)
            out[lay]=d<r; vok&=d>=rv
        return out,vok
    def route_net(s,net):
        idx=s.netidx[net]; w=WIDTH[netclass(net)]
        pads=[p for p in s.pads if p["net"]==net]
        # order: largest pads first, then nearest-neighbour chain
        pads.sort(key=lambda p:-min(p["w"],p["h"]))
        order=[pads[0]]; rest=pads[1:]
        while rest:
            last=order[-1]; rest.sort(key=lambda p:(p["x"]-last["x"])**2+(p["y"]-last["y"])**2); order.append(rest.pop(0))
        conn=set(s.padcells.get((order[0]["ref"],order[0]["pad"]),[]))
        def link(pd):
            for cells,other in s.prelinks.get((pd["ref"],pd["pad"]),[]):
                conn.update(cells)
                if other: conn.update(s.padcells.get(other,[]))
        link(order[0]); fails=0
        for pd in order[1:]:
            pw=min(w, max(0.3, min(pd["w"],pd["h"])-0.1)) if not pd["tht"] else w
            obs,vok=s.obstacles(idx,pw)
            # A pad ringed by its neighbours' keepouts (SOIC-8 at 1.27 mm, TSOT-23-6)
            # has no free cell to start from, so A* fails before it moves. Seed the
            # search with any hand-routed escape stub on this pad as well: prelinks
            # previously only extended the TARGET set, which helps the other end of
            # the net and does nothing for the pad that is actually trapped.
            src=list(s.padcells.get((pd["ref"],pd["pad"]),[]))
            for _cells,_o in s.prelinks.get((pd["ref"],pd["pad"]),[]):
                src.extend(_cells)
            path=s.astar(src,conn,obs,vok,idx)
            if path is None:
                print("  FAIL",net,pd["ref"],pd["pad"]); fails+=1; conn|=set(src); continue
            s.commit(path,pw,idx,net)
            conn|=set(src); conn|=set(path); link(pd)
        return fails
    def astar(s,src,targets,obs,vok,idx):
        tgt=set(targets)
        if not src or not tgt: return None
        tx=np.array([t[1] for t in tgt]); ty=np.array([t[2] for t in tgt])
        # heuristic: octile to nearest target (sampled)
        if len(tx)>400:
            sel=np.random.RandomState(0).choice(len(tx),400,replace=False); tx,ty=tx[sel],ty[sel]
        def h(i,j):
            dx=np.abs(tx-i); dy=np.abs(ty-j); return float(np.min(np.maximum(dx,dy)+0.414*np.minimum(dx,dy)))*0.95
        L={"F":0,"B":1}; LN="FB"
        openq=[]; g={}; came={}
        for (lay,i,j) in src:
            k=(L[lay],i,j); g[k]=0.0; heapq.heappush(openq,(h(i,j),0.0,k))
        VIA=14.0; LAYPEN={0:((1,0),(0,1)),1:((0,1),(1,0))}  # slight preference: F horizontal, B vertical
        moves=[(1,0,1.0),(-1,0,1.0),(0,1,1.0),(0,-1,1.0),(1,1,1.414),(1,-1,1.414),(-1,1,1.414),(-1,-1,1.414)]
        obsarr={0:obs["F"],1:obs["B"]}
        closed=set(); n=0
        while openq:
            f,gc,k=heapq.heappop(openq)
            if k in closed: continue
            closed.add(k); n+=1
            l,i,j=k
            if (LN[l],i,j) in tgt:
                path=[k]
                while k in came: k=came[k]; path.append(k)
                return [(LN[a],b,c) for a,b,c in reversed(path)]
            if n>900000: return None
            o=obsarr[l]
            for dx,dy,c in moves:
                ni,nj=i+dx,j+dy
                if ni<0 or nj<0 or ni>=NX or nj>=NY: continue
                if o[ni,nj] and (LN[l],ni,nj) not in tgt and (LN[l],ni,nj) not in src: continue
                if dx and dy and (o[i+dx,j] and o[i,j+dy]): continue
                # direction penalty
                pen=0.0
                if dy==0 and l==1: pen=0.15
                if dx==0 and l==0: pen=0.15
                ng=gc+c+pen; nk=(l,ni,nj)
                if ng<g.get(nk,1e18): g[nk]=ng; came[nk]=k; heapq.heappush(openq,(ng+h(ni,nj),ng,nk))
            # via
            if vok[i,j]:
                nl=1-l; nk=(nl,i,j); ng=gc+VIA
                if ng<g.get(nk,1e18): g[nk]=ng; came[nk]=k; heapq.heappush(openq,(ng+h(i,j),ng,nk))
        return None
    def commit(s,path,w,idx,net):
        # split into per-layer polylines, simplify collinear runs
        segs=[]; cur=[path[0]]
        for a,b in zip(path,path[1:]):
            if a[0]!=b[0]:
                segs.append(cur); s.vias.append((a[1]*G,a[2]*G,net)); s.mark_disk("F",a[1],a[2],VIA_D/2,idx); s.mark_disk("B",a[1],a[2],VIA_D/2,idx); cur=[b]
            else: cur.append(b)
        segs.append(cur)
        for poly in segs:
            if len(poly)<2: continue
            lay=poly[0][0]; pts=[(p[1],p[2]) for p in poly]
            simp=[pts[0]]
            for k in range(1,len(pts)-1):
                d1=(pts[k][0]-pts[k-1][0],pts[k][1]-pts[k-1][1]); d2=(pts[k+1][0]-pts[k][0],pts[k+1][1]-pts[k][1])
                if d1!=d2: simp.append(pts[k])
            simp.append(pts[-1])
            for a,b in zip(simp,simp[1:]):
                s.tracks.append((a[0]*G,a[1]*G,b[0]*G,b[1]*G,w,lay+".Cu",net))
            for (i,j) in pts: s.mark_disk(lay,i,j,w/2,idx)
    def mark_disk(s,lay,i,j,r,idx):
        rc=int(math.ceil(r/G))+1
        i0,i1=max(0,i-rc),min(NX,i+rc+1); j0,j1=max(0,j-rc),min(NY,j+rc+1)
        sub=s.cu[lay][i0:i1,j0:j1]
        X=(np.arange(i0,i1)*G)[:,None]; Y=(np.arange(j0,j1)*G)[None,:]
        m=((X-i*G)**2+(Y-j*G)**2)<=(r+0.13)**2
        sub[m&(sub==0)]=idx
    def run(s,first=()):
        names=[n for n in s.N if len(s.N[n])>1]
        # order: 12V first (wide), 5V, then signals, GND last; nets that failed in a previous pass go first
        pri={"12V":0,"5V":1,"RS485":2,"Default":3,"GND":4}   # RS485 pairs routed early: keep A/B short and together
        names.sort(key=lambda n:(n not in first,pri[netclass(n)],-len(s.N[n])))
        fails=0; s.failed=[]
        for n in names:
            f=s.route_net(n); fails+=f
            if f: s.failed.append(n)
            print(f"routed {n:16s} pads={len(s.N[n])} fails={f} tracks={len(s.tracks)} vias={len(s.vias)}",flush=True)
        return fails

def route_all(max_passes=6):
    first=[]
    for p in range(max_passes):
        r=Router(); fails=r.run(first)
        print(f"pass {p+1}: fails={fails}",flush=True)
        if fails==0: return r
        first=r.failed+[n for n in first if n not in r.failed]
    return r

if __name__=="__main__":
    import sexp, pickle
    r=route_all(); fails=len(r.failed)
    # drop tiny stubs with a free end (router artefacts at via/pad boundaries)
    ends={}
    for t in r.tracks:
        for e in ((round(t[0],3),round(t[1],3)),(round(t[2],3),round(t[3],3))): ends[e]=ends.get(e,0)+1
    for v in r.vias: ends[(round(v[0],3),round(v[1],3))]=ends.get((round(v[0],3),round(v[1],3)),0)+1
    padpts={(round(p["x"],3),round(p["y"],3)) for p in r.pads}
    def free(e): return ends.get(e,0)<=1 and not any(abs(e[0]-q[0])<0.9 and abs(e[1]-q[1])<0.9 for q in padpts)
    keep=[t for t in r.tracks if not (math.hypot(t[2]-t[0],t[3]-t[1])<0.3 and (free((round(t[0],3),round(t[1],3))) or free((round(t[2],3),round(t[3],3)))))]
    print("stub cleanup removed",len(r.tracks)-len(keep)); r.tracks=keep
    print("TOTAL FAILS",fails,"tracks",len(r.tracks),"vias",len(r.vias))
    pickle.dump((r.tracks,r.vias),open("routes.pkl","wb"))
    open("../"+PROJECT+".kicad_pcb","w").write(sexp.dump(gen_pcb.build(r.tracks,r.vias))+"\n"); gen_pcb.write_pro("../"+PROJECT+".kicad_pro")
