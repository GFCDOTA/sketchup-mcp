import contextlib, io, json, time
from tools.furnish_apartment import collect_boxes
import tools.orchestration.furnish_apartment as fa
from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
from tools.orchestration import intelligent_pipeline as ip
from core.pipeline_contracts import CapabilityLedger
from tools.room_type import classify_rooms
from tools.validation.functional_clearance import collect_interfaces
con=json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
with contextlib.redirect_stdout(io.StringIO()):
    boxes,summary=collect_boxes(con); ifaces=collect_interfaces(con,boxes)
rooms={r["id"]:r for r in classify_rooms(con)}
out={}
for rid in ("r005","r006","r007"):
    r=rooms[rid]; brain=fa.BRAINS.get(r["room_type"]); t=time.time()
    o=ip.plan_room(con,boxes,ifaces,rid,r["room_type"],str(r["name"]),ip._builder_symbol(brain),CapabilityLedger())
    p=o["proposal"]
    out[rid]={"name":str(r["name"]),"status":o["status"],"candidates":p.candidates_total,"seconds":round(time.time()-t),
              "hard_violations":[{k:(v if isinstance(v,(int,float,str,type(None))) else str(v)) for k,v in x.items()} for x in p.hard_violations],
              "moves":[m["object_id"] for m in p.moves],"metrics":{k:(v if isinstance(v,(int,float,str)) else str(v)) for k,v in (p.metrics or {}).items()}}
    print(rid,json.dumps(out[rid],ensure_ascii=False),flush=True)
open("runs/r6e_details.json","w",encoding="utf-8").write(json.dumps(out,indent=1,ensure_ascii=False))
