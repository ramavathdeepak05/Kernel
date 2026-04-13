"""
Generate a layered architecture diagram from graph.db.
Modules are fixed to their ALIS architectural layer (1-5).
Outputs: .code-review-graph/module_graph.html
"""
import sqlite3, re, json
from collections import defaultdict

DB  = r".code-review-graph\graph.db"
OUT = r".code-review-graph\module_graph.html"

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
SERVER_RE = re.compile(r'ALIS[\\/]server[\\/](\w+)[\\/]')

def get_module(path):
    m = SERVER_RE.search(path or "")
    return m.group(1) if m else None

LAYERS = {
    1: {"label": "L1 — Infrastructure",    "modules": ["core", "db_service", "integrations", "rules"]},
    2: {"label": "L2 — Domain Services",   "modules": ["admissions","academics","examinations","finance","hr","student_services","alumni","phd","convocation","consent"]},
    3: {"label": "L3 — Cross-cutting",     "modules": ["communication","regulatory","reporting","process_engine","migration","agents"]},
    4: {"label": "L4 — Orchestration",     "modules": ["tasks","tools"]},
    5: {"label": "L5 — API",               "modules": ["api"]},
}
COLORS = {
    "core":"#64748b","db_service":"#475569","integrations":"#94a3b8","rules":"#7c3aed",
    "admissions":"#4e79a7","academics":"#59a14f","examinations":"#f28e2b","finance":"#e15759",
    "hr":"#76b7b2","student_services":"#edc948","alumni":"#b07aa1","phd":"#d37295",
    "convocation":"#a0cbe8","consent":"#8cd17d","communication":"#ff9da7","regulatory":"#9c755f",
    "reporting":"#bab0ac","process_engine":"#f1ce63","migration":"#b6992d","agents":"#499894",
    "tasks":"#86bcb6","tools":"#ffbe7d","api":"#dc2626",
}
LABELS = {
    "core":"Core","db_service":"DB","integrations":"Integrations","rules":"Rules",
    "admissions":"Admissions","academics":"Academics","examinations":"Examinations",
    "finance":"Finance","hr":"HR","student_services":"Student Svcs","alumni":"Alumni",
    "phd":"PhD","convocation":"Convocation","consent":"Consent",
    "communication":"Comms","regulatory":"Regulatory","reporting":"Reporting",
    "process_engine":"Process Eng","migration":"Migration","agents":"AI Agents",
    "tasks":"Celery","tools":"Tools","api":"API",
}

mod_layer = {mod: lid for lid, info in LAYERS.items() for mod in info["modules"]}
module_sizes = defaultdict(int)
for r in db.execute("SELECT file_path FROM nodes").fetchall():
    m = get_module(r["file_path"])
    if m: module_sizes[m] += 1

module_edges = defaultdict(int)
for r in db.execute("SELECT source_qualified, target_qualified FROM edges WHERE kind IN ('CALLS','IMPORTS_FROM','IMPORTS')").fetchall():
    sm, tm = get_module(r["source_qualified"]), get_module(r["target_qualified"])
    if sm and tm and sm != tm: module_edges[(sm, tm)] += 1

CW, CH = 1400, 820
MX, MY = 100, 70
layer_ids = sorted(LAYERS.keys())
layer_x = {lid: MX + i*(CW-2*MX)/(len(layer_ids)-1) for i, lid in enumerate(layer_ids)}

nodes = []
for mod, size in module_sizes.items():
    layer = mod_layer.get(mod, 3)
    mods  = LAYERS.get(layer, {}).get("modules", [mod])
    idx   = mods.index(mod) if mod in mods else 0
    n     = len(mods)
    x     = layer_x.get(layer, CW//2)
    y     = MY + idx*(CH-2*MY)/max(n-1,1) if n > 1 else CH//2
    nodes.append({"id":mod,"label":LABELS.get(mod,mod),"color":COLORS.get(mod,"#888"),
                  "x":round(x),"y":round(y),"size":max(14,min(36,size//3)),
                  "nodeCount":size,"layer":layer})

links = [{"source":sm,"target":tm,"weight":w,"width":max(1,min(8,w//8))}
         for (sm,tm),w in module_edges.items() if w >= 3]

data_json = json.dumps({"nodes":nodes,"links":links,
                         "layers":{str(k):v["label"] for k,v in LAYERS.items()}})

html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>ALIS Architecture</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;color:#e2e8f0;font-family:system-ui,sans-serif;overflow:hidden}}
svg{{width:100vw;height:100vh}}
.lbl{{font-size:9px;font-weight:700;fill:#fff;text-anchor:middle;dominant-baseline:central;pointer-events:none}}
.layer-lbl{{font-size:11px;fill:#475569;font-weight:600;text-anchor:middle}}
.divider{{stroke:#1e293b;stroke-width:1;stroke-dasharray:5,5}}
.tip{{position:absolute;background:#1e2130;border:1px solid #334155;border-radius:8px;
      padding:12px;font-size:13px;pointer-events:none;opacity:0;transition:opacity .15s;
      min-width:200px;box-shadow:0 8px 32px rgba(0,0,0,.6)}}
.tip strong{{display:block;font-size:14px;margin-bottom:6px;color:#a5b4fc}}
.tip .sub{{color:#64748b;font-size:11px;margin-bottom:6px}}
#hd{{position:absolute;top:16px;left:18px}}
#hd h1{{font-size:17px;font-weight:700;color:#a5b4fc}}
#hd p{{font-size:11px;color:#475569;margin-top:3px}}
</style></head>
<body>
<div id="hd"><h1>ALIS Module Architecture</h1><p>Fixed layer layout · L1 (left) → L5 (right) · hover for details</p></div>
<div class="tip" id="tip"></div>
<svg id="sv"></svg>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const d={data_json};
const W=window.innerWidth,H=window.innerHeight,sx=W/1400,sy=H/820;
const nm={{}};d.nodes.forEach(n=>{{n.px=n.x*sx;n.py=n.y*sy;nm[n.id]=n;}});
const svg=d3.select("#sv").attr("width",W).attr("height",H);
const root=svg.append("g");
svg.call(d3.zoom().scaleExtent([.3,4]).on("zoom",e=>root.attr("transform",e.transform)));

// Layer dividers & labels
const lx=[...new Set(d.nodes.map(n=>n.px))].sort((a,b)=>a-b);
for(let i=0;i<lx.length-1;i++){{
  root.append("line").attr("class","divider")
    .attr("x1",(lx[i]+lx[i+1])/2).attr("y1",0)
    .attr("x2",(lx[i]+lx[i+1])/2).attr("y2",H);
}}
Object.entries(d.layers).forEach(([lid,label])=>{{
  const ms=d.nodes.filter(n=>n.layer===+lid);
  if(!ms.length)return;
  root.append("text").attr("class","layer-lbl")
    .attr("x",d3.mean(ms,n=>n.px)).attr("y",18).text(label);
}});

// Curved edges
svg.append("defs").append("marker").attr("id","ar").attr("viewBox","0 -4 8 8")
  .attr("refX",20).attr("refY",0).attr("markerWidth",5).attr("markerHeight",5)
  .attr("orient","auto").append("path").attr("d","M0,-4L8,0L0,4").attr("fill","#334155");

root.append("g").selectAll("path").data(d.links).join("path")
  .attr("fill","none").attr("stroke",l=>{{const s=nm[l.source];return s?s.color+"55":"#33415566";}})
  .attr("stroke-width",l=>l.width).attr("marker-end","url(#ar)")
  .attr("d",l=>{{
    const s=nm[l.source],t=nm[l.target];if(!s||!t)return"";
    const mx=(s.px+t.px)/2;
    return `M${{s.px}},${{s.py}} C${{mx}},${{s.py}} ${{mx}},${{t.py}} ${{t.px}},${{t.py}}`;
  }});

// Nodes
const ng=root.append("g").selectAll("g").data(d.nodes).join("g")
  .attr("transform",n=>`translate(${{n.px}},${{n.py}})`).style("cursor","pointer");
ng.append("circle").attr("r",n=>n.size+7).attr("fill",n=>n.color+"1a").attr("stroke",n=>n.color+"44").attr("stroke-width",1.5);
ng.append("circle").attr("r",n=>n.size).attr("fill",n=>n.color).attr("stroke","#0d1117").attr("stroke-width",2);
ng.append("text").attr("class","lbl").attr("font-size",n=>Math.min(10,n.size*.6)+"px").text(n=>n.label);

// Tooltip
const tip=document.getElementById("tip");
ng.on("mouseover",(e,n)=>{{
  const out=d.links.filter(l=>l.source===n.id).map(l=>nm[l.target]?.label).filter(Boolean);
  const inn=d.links.filter(l=>l.target===n.id).map(l=>nm[l.source]?.label).filter(Boolean);
  tip.innerHTML=`<strong>${{n.label}}</strong><div class="sub">Layer ${{n.layer}} · ${{n.nodeCount}} nodes</div>`
    +(out.length?`<div style="color:#94a3b8;font-size:11px">Depends on:</div><div>${{out.join(", ")}}</div>`:"")
    +(inn.length?`<div style="color:#94a3b8;font-size:11px;margin-top:6px">Used by:</div><div>${{inn.join(", ")}}</div>`:"");
  tip.style.opacity=1;tip.style.left=(e.pageX+16)+"px";tip.style.top=(e.pageY-10)+"px";
}}).on("mousemove",e=>{{tip.style.left=(e.pageX+16)+"px";tip.style.top=(e.pageY-10)+"px";}})
  .on("mouseout",()=>tip.style.opacity=0);
</script></body></html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Generated: {OUT}")
print(f"  {len(nodes)} modules · {len(links)} edges (>=3 weight)")
