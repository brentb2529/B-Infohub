"""Minimal KiCad S-expression parser / serializer."""
import re
TOK = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))', re.S)

def parse(text):
    stack=[[]]; pos=0; n=len(text)
    while pos<n:
        m=TOK.match(text,pos)
        if not m:
            if text[pos:].strip()=='' : break
            raise ValueError(text[pos:pos+40])
        pos=m.end()
        if m.group(1): stack.append([])
        elif m.group(2):
            l=stack.pop(); stack[-1].append(l)
        elif m.group(3): stack[-1].append(m.group(3))   # keep quoted string with quotes
        elif m.group(4): stack[-1].append(m.group(4))
    return stack[0]

def dump(node, ind=0):
    if isinstance(node,str): return node
    if not node: return "()"
    parts=[]; inner=[]
    simple = all(isinstance(c,str) for c in node)
    if simple: return "("+" ".join(node)+")"
    s="("+ (node[0] if isinstance(node[0],str) else dump(node[0],ind+1))
    i=1
    # keep leading atoms on the same line
    while i<len(node) and isinstance(node[i],str): s+=" "+node[i]; i+=1
    for c in node[i:]:
        s+="\n"+"\t"*(ind+1)+dump(c,ind+1)
    return s+"\n"+"\t"*ind+")"

def q(s):  # quote a string
    return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
def unq(s):
    if isinstance(s,str) and len(s)>=2 and s[0]=='"': return s[1:-1].replace('\\"','"').replace('\\\\','\\')
    return s
def find(node,key):
    return [c for c in node if isinstance(c,list) and c and c[0]==key]
def find1(node,key):
    f=find(node,key); return f[0] if f else None
def load_symbol(libfile, name):
    txt=open(libfile).read()
    tree=parse(txt)[0]
    for c in tree:
        if isinstance(c,list) and c and c[0]=='symbol' and unq(c[1])==name: return c
    raise KeyError(name)
def load_footprint(path):
    return parse(open(path).read())[0]
