"""Seeded synthetic log generator for demos and repeatable benchmarks."""
import argparse, json, random
from datetime import datetime, timedelta, timezone
from pathlib import Path

def generate(path="data/sample/sample.jsonl", count=120, seed=42):
    rng=random.Random(seed); start=datetime(2026,11,12,10,tzinfo=timezone.utc); services=["api","payments","auth","worker"]; levels=["INFO","INFO","INFO","WARNING","ERROR","CRITICAL"]
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); labels=[]
    with open(path,"w",encoding="utf-8") as out:
        base=[]
        for i in range(count):
            row={"event_id":f"evt-{i:07d}","timestamp":(start+timedelta(seconds=(count-i if i%17==0 else i))).isoformat().replace("+00:00","Z"),"level":rng.choice(levels),"service":rng.choice(services),"message":f"Synthetic event {i}","latency_ms":rng.choice([0,12,35,90,210,None])}
            if i%37==0: row["extra_context"]="schema drift sample"
            if i%41==0: row["timestamp"]="not-a-timestamp"
            if i%43==0: row["latency_ms"]=-1
            base.append(row)
        line_number=0
        for row in base:
            line_number+=1
            out.write(json.dumps(row)+"\n")
            invalid = row["timestamp"] == "not-a-timestamp" or (row["latency_ms"] is not None and row["latency_ms"] < 0)
            labels.append({"source_line":line_number,"event_id":row["event_id"],"expected_category":"INVALID" if invalid else "ACCEPTED"})
            if row["event_id"].endswith("0000010"):
                line_number+=1; out.write(json.dumps(row)+"\n")
                labels.append({"source_line":line_number,"event_id":row["event_id"],"expected_category":"DUPLICATE"})
        if count>=10:
            line_number+=1; out.write('{malformed json}\n')
            labels.append({"source_line":line_number,"event_id":None,"expected_category":"MALFORMED"})
    counts={}
    for label in labels: counts[label["expected_category"]]=counts.get(label["expected_category"],0)+1
    Path(path.with_name(path.stem+"_expected.json")).write_text(json.dumps({"seed":seed,"source_file":path.name,"input_count":len(labels),"counts":counts,"records":labels},indent=2),encoding="utf-8")
    return path

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--output",default="data/sample/sample.jsonl"); p.add_argument("--count",type=int,default=120); p.add_argument("--seed",type=int,default=42); a=p.parse_args(); print(generate(a.output,a.count,a.seed))
