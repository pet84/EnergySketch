# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Pure validation/planning for the original whitelisted LIVE command protocol."""
import hashlib
import copy
import math
import re
import time
from .live import encode, REF

SIGNATURE_KEYS = ("protocol","id","action","modelId","connectionId","baseRevision","payload","createdAt","expiresAt")


def signature(command):
    return encode([[key,command.get(key)] for key in SIGNATURE_KEYS])


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def validate_command(command,model_id,connection,revision,now_ms=None):
    now_ms = time.time()*1000 if now_ms is None else now_ms
    if not isinstance(command,dict) or type(command.get("protocol")) is not int or command["protocol"] != 1 or not isinstance(command.get("id"),str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,70}",command["id"]) or command.get("action") not in ("box","pyramid","colors","import_model","sync_model"):
        raise ValueError("Neplatný příkaz APP.")
    if command.get("modelId") != model_id or command.get("connectionId") != connection:
        raise ValueError("Příkaz patří jinému modelu nebo propojení.")
    if type(command.get("baseRevision")) is not int or command["baseRevision"] != revision:
        raise ValueError("Model se mezitím změnil; zopakujte příkaz z aktuální revize.")
    if not number(command.get("expiresAt")) or now_ms > command["expiresAt"]:
        raise ValueError("Příkaz vypršel; odešlete jej znovu z APP.")
    payload = command.get("payload")
    if command["action"] == "import_model":
        validate_model(payload)
        return
    if command["action"] == "sync_model":
        validate_sync(payload)
        return
    if not isinstance(payload,dict):
        raise ValueError("Chybí parametry testovacího příkazu.")
    if command["action"] == "colors" and not payload:
        return
    expected = [3000,2000,2500] if command["action"] == "box" else [3000,3000,3000]
    origin = payload.get("origin")
    if payload.get("size") != expected or not isinstance(origin,list) or len(origin) != 3 or not all(number(v) and abs(v) < 1e8-10000 for v in origin):
        raise ValueError("Neplatné rozměry testovacího tělesa.")


def solid_rings(action,origin,size):
    x,y,z = size
    points = [[0,0,0],[x,0,0],[x,y,0],[0,y,0]]
    indices = [[3,2,1,0]]
    if action == "box":
        points += [[0,0,z],[x,0,z],[x,y,z],[0,y,z]]
        indices += [[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    elif action == "pyramid":
        points += [[x/2,y/2,z]]
        indices += [[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
    else:
        raise ValueError("Nepodporované testovací těleso.")
    return [[[points[k][j]+origin[j] for j in range(3)] for k in ring] for ring in indices]


def native_id(project,zone):
    return "app_" + hashlib.sha256(encode([project,zone])).hexdigest()[:40]


def ref(value):
    return isinstance(value,str) and REF.fullmatch(value) is not None


def validate_model(p):
    if not isinstance(p,dict) or not ref(p.get("projectId")) or type(p.get("sourceRevision")) is not int or p["sourceRevision"] < 0 or p.get("version") not in ("accepted","working"):
        raise ValueError("Neplatný model APP.")
    arrays = [p.get(key) for key in ("zones","faces","materials")]
    if not all(isinstance(items,list) and items and all(isinstance(v,dict) and ref(v.get("id")) for v in items) for items in arrays):
        raise ValueError("Model potřebuje zóny, plochy a materiály s platnými ID.")
    zones,faces,materials = arrays
    if len(faces)>1500 or len(zones)*3+len(materials)+1>100 or len(encode(p))>3*1024*1024:
        raise ValueError("Model překročil limit jedné dávky.")
    if any(len({v["id"] for v in items}) != len(items) for items in arrays):
        raise ValueError("Duplicitní ID modelu.")
    for zone in zones:
        if zone.get("nativeId") != native_id(p["projectId"],zone["id"]) or not isinstance(zone.get("name"),str) or not 1<=len(zone["name"])<=120:
            raise ValueError("Neplatná zóna.")
    for material in materials:
        color = material.get("color")
        if not isinstance(material.get("type"),str) or type(material.get("variant")) is not int or material["variant"]<=0 or not isinstance(material.get("name"),str) or len(material["name"])>160 or not isinstance(color,list) or len(color)!=3 or not all(type(v) is int and 0<=v<=255 for v in color):
            raise ValueError("Neplatný materiál APP.")
        for key in ("u","g"):
            v = material.get(key)
            if v is not None and (not number(v) or v<0 or key=="g" and v>1):
                raise ValueError("Neplatné U/g materiálu APP.")
    zone_ids,face_ids,material_ids = ({v["id"] for v in items} for items in arrays)
    for face in faces:
        rings = face.get("rings")
        if face.get("zoneId") not in zone_ids or face.get("constructionId") not in material_ids or face.get("hostFaceId") is not None and face["hostFaceId"] not in face_ids:
            raise ValueError("Chybí vazba plochy na zónu, konstrukci nebo hostitele.")
        if not isinstance(rings,list) or not 1<=len(rings)<=100 or not all(isinstance(r,list) and 3<=len(r)<=10000 and all(isinstance(q,list) and len(q)==3 and all(number(v) and abs(v)<1e8 for v in q) for q in r) for r in rings):
            raise ValueError("Neplatné obrysy plochy APP.")
        if face.get("confidence") not in ("documented","inferred","unresolved") or not isinstance(face.get("source"),str) or len(face["source"])>1000:
            raise ValueError("Neplatný původ plochy APP.")
        validate_rings(rings)


def validate_rings(rings):
    """Millimetre geometry: planar, simple, nonintersecting internal holes."""
    origin = rings[0][0]
    relative = [[tuple(p[i]-origin[i] for i in range(3)) for p in ring] for ring in rings]
    outer = relative[0]
    normal = [0.,0.,0.]
    for a,b in zip(outer,[*outer[1:],outer[0]]):
        for i in range(3):
            normal[i] += a[(i+1)%3]*b[(i+2)%3]-a[(i+2)%3]*b[(i+1)%3]
    length = math.sqrt(sum(v*v for v in normal))
    if length<1e-8:
        raise ValueError("Plocha APP je degenerovaná.")
    normal = [v/length for v in normal]
    if any(abs(sum(p[i]*normal[i] for i in range(3)))>.1 for ring in relative for p in ring):
        raise ValueError("Plocha nebo její otvory nejsou v jedné rovině (0,1 mm).")
    drop = max(range(3),key=lambda i:abs(normal[i]))
    flat = [[tuple(p[i] for i in range(3) if i!=drop) for p in ring] for ring in relative]

    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])

    def on(a,b,p):
        return abs(cross(a,b,p))<1e-8 and all(min(a[i],b[i])-1e-8<=p[i]<=max(a[i],b[i])+1e-8 for i in range(2))

    def intersection(a,b,c,d):
        return (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)

    def segments(ring):
        return list(zip(ring,[*ring[1:],ring[0]]))

    def inside(point,ring):
        yes = False
        x,y = point
        for a,b in segments(ring):
            if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
                yes = not yes
        return yes

    for ring,ring3 in zip(flat,relative):
        edges = segments(ring)
        for i,(a,b) in enumerate(edges):
            if sum((ring3[i][k]-ring3[(i+1)%len(ring3)][k])**2 for k in range(3))<.0001:
                raise ValueError("Obrys obsahuje příliš krátkou hranu (0,01 mm).")
            for j in range(i+2,len(edges)):
                if i==0 and j==len(edges)-1:
                    continue
                if intersection(a,b,*edges[j]):
                    raise ValueError("Obrys plochy protíná nebo se dotýká sám sebe.")
    for i,hole in enumerate(flat[1:],1):
        if not inside(hole[0],flat[0]):
            raise ValueError("Otvor neleží uvnitř plochy.")
        for j,other in enumerate(flat[:i]):
            if any(intersection(a,b,c,d) for a,b in segments(hole) for c,d in segments(other)):
                raise ValueError("Obrysy otvorů se protínají nebo dotýkají hranice.")
            if j>0 and (inside(hole[0],other) or inside(other[0],hole)):
                raise ValueError("Otvory se překrývají nebo jsou vnořené.")


def binding(payload,face,command):
    return {"projectId":payload["projectId"],"zoneId":face["zoneId"],"faceId":face["id"],
            "constructionId":face["constructionId"],"hostFaceId":face.get("hostFaceId"),
            "sourceRevision":payload["sourceRevision"],"transferId":command["id"]}


def model_material_name(spec,names):
    from .materials import TYPES,WINDOW_TYPES,build_name,next_free_number
    from .core import parse_material_name
    typ = spec["type"].upper()
    if typ not in dict(TYPES):
        raise ValueError("Neznámý typ konstrukce APP.")
    if typ not in WINDOW_TYPES and spec.get("g") is not None:
        raise ValueError("g patří pouze k oknům; nejprve jej v APP odstraňte.")
    name = build_name({"typ":typ,"cislo":next_free_number(names,typ),"var":"V"+str(spec["variant"]),
                       "u":"" if spec.get("u") is None else str(spec["u"]),
                       "g":"" if spec.get("g") is None else str(spec["g"]),"popis":spec["name"]})
    if len(name)>240 or not parse_material_name(name)["typ"]:
        raise ValueError("Název materiálu přesahuje 240 znaků nebo jej nepodporuje původní parser.")
    return name


def same_ring(a,b,reverse=False,tolerance=.02):
    return len(a)==len(b) and any(all(all(abs(p[k]-b[(start+(-i if reverse else i))%len(b)][k])<=tolerance for k in range(3))
                                    for i,p in enumerate(a)) for start in range(len(b)))


def same_rings(a,b):
    if len(a)!=len(b) or not same_ring(a[0],b[0]):
        return False
    holes = list(b[1:])
    for ring in a[1:]:
        for i,hole in enumerate(holes):
            if same_ring(ring,hole) or same_ring(ring,hole,True):
                holes.pop(i)
                break
        else:
            return False
    return True


def native_path(path):
    return isinstance(path,list) and len(path)<=32 and all(isinstance(v,str) and re.fullmatch(r"[1-9]\d*",v) for v in path)


def native_ref(value):
    return isinstance(value,str) and value.startswith("face:") and native_path(value[5:].split("/"))


def validate_sync(p):
    if not isinstance(p,dict) or p.get("purpose")!="model-sync" or not ref(p.get("projectId")) or type(p.get("sourceRevision")) is not int:
        raise ValueError("Neplatná synchronizace modelu.")
    if not all(isinstance(p.get(k),list) for k in ("faces","removed","expected","materials","zones")) or len(p["faces"])+len(p["removed"])>1500 or len(p["zones"])>25:
        raise ValueError("Neplatná změnová dávka.")
    if not all(isinstance(f,dict) for f in p["faces"]):
        raise ValueError("Neplatná plocha změny.")
    ids = [f.get("id") for f in p["faces"]]+p["removed"]
    if not ids or not all(ref(v) for v in ids) or len(set(ids))!=len(ids):
        raise ValueError("Duplicitní nebo neplatná ID změny.")
    if p["faces"]:
        check = copy.deepcopy(p)
        for f in check["faces"]:
            f["hostFaceId"] = None
        validate_model(check)
    if not all(isinstance(z,dict) and ref(z.get("id")) and z.get("nativeId")==native_id(p["projectId"],z["id"]) and not z["id"].startswith("epcp_") for z in p["zones"]):
        raise ValueError("Neplatná komponenta zóny.")
    if any(f.get("hostFaceId") is not None and not ref(f["hostFaceId"]) for f in p["faces"]):
        raise ValueError("Neplatný hostitel.")
    expected = p["expected"]
    if p.get("addressing")=="native-path-v1":
        for m in p["materials"]:
            if not isinstance(m,dict) or "nativeMaterial" in m and (not isinstance(m["nativeMaterial"],str) or len(m["nativeMaterial"])>240) or "alpha" in m and (not number(m["alpha"]) or not 0<=m["alpha"]<=1):
                raise ValueError("Neplatný původní materiál nebo průhlednost.")
        targets,containers = p.get("targets"),p.get("containers")
        zone_ids = {z["id"] for z in p["zones"]}
        if not isinstance(targets,list) or not all(isinstance(t,dict) and t.get("id") in ids and native_ref(t.get("nativeId")) and t.get("zoneId") in zone_ids for t in targets) or len({t["id"] for t in targets})!=len(targets) or len({t["nativeId"] for t in targets})!=len(targets):
            raise ValueError("Neplatné adresy ploch.")
        if not all(isinstance(e,dict) and e.get("kind")=="face" and any(t["nativeId"]==e.get("id") for t in targets) and (not e.get("binding") or e["binding"].get("projectId")==p["projectId"]) for e in expected) or sorted(e["id"] for e in expected)!=sorted(t["nativeId"] for t in targets) or any(not any(t["id"]==v for t in targets) for v in p["removed"]):
            raise ValueError("Neplatný původní snímek.")
        if not isinstance(containers,list) or not 1<=len(containers)<=100 or not all(isinstance(c,dict) and ref(c.get("key")) and (c.get("path") is None or native_path(c["path"])) and c.get("zoneId") in zone_ids and all(isinstance(c.get(k),list) for k in ("faceIds","removeIds","identities")) for c in containers):
            raise ValueError("Neplatné kontejnery.")
        if len({c["key"] for c in containers})!=len(containers) or sorted(v for c in containers for v in c["faceIds"])!=sorted(f["id"] for f in p["faces"]) or sorted(v for c in containers for v in c["removeIds"])!=sorted(p["removed"]):
            raise ValueError("Nejednoznačné kontejnery.")
        for c in containers:
            mapping = c["identities"]
            if not all(isinstance(i,dict) and ref(i.get("id")) and native_ref(i.get("nativeId")) and i["nativeId"][5:].split("/")[:-1]==c["path"] for i in mapping) or len({i["id"] for i in mapping})!=len(mapping) or len({i["nativeId"] for i in mapping})!=len(mapping):
                raise ValueError("Neplatná mapa identit.")
            if not all(t["zoneId"]==c["zoneId"] and any(i["id"]==t["id"] and i["nativeId"]==t["nativeId"] for i in mapping) for t in targets if t["id"] in c["faceIds"]+c["removeIds"]) or not all(f["zoneId"]==c["zoneId"] for f in p["faces"] if f["id"] in c["faceIds"]):
                raise ValueError("Plocha patří jiné komponentě nebo zóně.")
    elif not all(isinstance(e,dict) and e.get("kind")=="face" and isinstance(e.get("binding"),dict) and e["binding"].get("projectId")==p["projectId"] and e["binding"].get("faceId") in ids for e in expected) or len({e["binding"]["faceId"] for e in expected})!=len(expected) or any(not any(e["binding"]["faceId"]==v for e in expected) for v in p["removed"]):
        raise ValueError("Nejednoznačná původní data.")
    if len(encode(p))>3*1024*1024:
        raise ValueError("Dávka je příliš velká.")


def validate_report(p):
    validate_model(p)
    ids = [f["id"] for f in p["faces"]]
    if p.get("purpose")!="floor-report-layout" or p.get("layerName")!="EP/CP" or not all(z["id"].startswith("epcp_") for z in p["zones"]):
        raise ValueError("Povoleny jsou pouze reportové zóny EP/CP.")
    if not all(isinstance(p.get(k),list) and len(p[k])==len(ids) for k in ("expected","moves")) or not all(isinstance(e,dict) and isinstance(e.get("binding"),dict) and e["binding"].get("faceId") in ids for e in p["expected"]) or not all(isinstance(m,dict) and m.get("faceId") in ids for m in p["moves"]) or len({m["faceId"] for m in p["moves"]})!=len(ids) or len({e["binding"]["faceId"] for e in p["expected"]})!=len(ids):
        raise ValueError("Chybí jednoznačné původní plochy nebo posuny.")
    for m in p["moves"]:
        face = next(f for f in p["faces"] if f["id"]==m["faceId"])
        if m.get("zoneId")!=face["zoneId"] or not ref(m.get("floorId")) or not all(number(m.get(k)) and abs(m[k])<1e8 for k in ("elevationMm","cutMm")) or not isinstance(m.get("delta"),list) or len(m["delta"])!=3 or not all(number(v) and abs(v)<1e8 for v in m["delta"]):
            raise ValueError("Neplatný posun nebo podlaží.")
