import contextlib, io, json, sys, time
import tools.rooms.bathroom.layout as bl
from tools.furnish_apartment import collect_boxes
import tools.orchestration.furnish_apartment as fa
from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
from tools.orchestration import intelligent_pipeline as ip
from core.pipeline_contracts import CapabilityLedger
from tools.room_type import classify_rooms
from tools.validation.functional_clearance import collect_interfaces
con=json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
orig=bl._box_front
def variant(opening_m):
    # interface do box: abertura livre = fixw - 0,05 m (folha sobrepoe 5 cm). Para abertura A: fixw = A + 0,05, SEM o teto de 45% da frente
    def f(b,door_c):
        horiz,a0,a1,front,back,sin,fixw,leaf_lo=orig(b,door_c)
        return horiz,a0,a1,front,back,sin,bl.M(opening_m+0.05),leaf_lo
    return f
out={}
for rid in ("r005","r006"):
    for label,op in (("abertura 0,60",0.60),("abertura 0,70",0.70)):
        bl._box_front=variant(op)
        with contextlib.redirect_stdout(io.StringIO()):
            boxes,summary=collect_boxes(con); ifaces=collect_interfaces(con,boxes)
        rooms={r["id"]:r for r in classify_rooms(con)}; r=rooms[rid]; brain=fa.BRAINS.get(r["room_type"])
        t=time.time()
        o=ip.plan_room(con,boxes,ifaces,rid,r["room_type"],str(r["name"]),ip._builder_symbol(brain),CapabilityLedger())
        p=o["proposal"]
        rec={"room":rid,"alt":label,"status":o["status"],"candidates":p.candidates_total,"seconds":round(time.time()-t),
             "violations":[[v.get("code"),str(v.get("detail"))[:90],v.get("measured")] for v in p.hard_violations],"moves":[m["object_id"] for m in p.moves]}
        out[f"{rid}:{label}"]=rec; print(json.dumps(rec,ensure_ascii=False),flush=True)
bl._box_front=orig
open("runs/r6g_opening.json","w",encoding="utf-8").write(json.dumps(out,indent=1,ensure_ascii=False))
