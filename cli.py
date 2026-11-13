"""Small command line entry point."""
import argparse, csv, json
from contextlib import closing
from pathlib import Path
from analytics import summary
from database import connect
from generator import generate
from pipeline import run_pipeline
from export_utils import spreadsheet_safe_cell
from retention import prune_old_runs

def main():
    p=argparse.ArgumentParser(description="LogLens log analytics pipeline"); sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("init-db")
    g=sub.add_parser("generate"); g.add_argument("--output",default="data/sample/sample.jsonl"); g.add_argument("--count",type=int,default=120); g.add_argument("--seed",type=int,default=42)
    r=sub.add_parser("run"); r.add_argument("input"); r.add_argument("--db",default="data/loglens.db"); r.add_argument("--batch-size",type=int,default=1000)
    a=sub.add_parser("analytics"); a.add_argument("--db",default="data/loglens.db")
    e=sub.add_parser("export"); e.add_argument("kind",choices=["processed","rejected"]); e.add_argument("--db",default="data/loglens.db"); e.add_argument("--output",required=True)
    c=sub.add_parser("prune", help="Report or remove runs older than a retention period")
    c.add_argument("--older-than-days", type=int, required=True)
    c.add_argument("--db", default="data/loglens.db")
    c.add_argument("--apply", action="store_true", help="Delete matching run data; omitted means dry-run only")
    args=p.parse_args()
    if args.cmd=="init-db": connect().close(); print("Initialized data/loglens.db")
    elif args.cmd=="generate": print(generate(args.output,args.count,args.seed))
    elif args.cmd=="run":
        result = run_pipeline(args.input,args.db,args.batch_size)
        print(json.dumps(result,indent=2))
        if result["status"] == "FAILED":
            raise SystemExit(1)
    elif args.cmd=="analytics":
        s=summary(args.db); print(json.dumps({k:v for k,v in s.items() if not hasattr(v,"to_dict")},indent=2))
    elif args.cmd=="export":
        table="processed_logs" if args.kind=="processed" else "rejected_records"
        with closing(connect(args.db)) as db:
            cursor=db.execute(f"SELECT * FROM {table}")
            columns=[item[0] for item in cursor.description]
            rows=cursor.fetchall()
        out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
        with out.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow([spreadsheet_safe_cell(value) for value in columns])
            w.writerows([[spreadsheet_safe_cell(value) for value in row] for row in rows])
        print(f"Exported {len(rows)} rows to {out}")
    elif args.cmd=="prune":
        result = prune_old_runs(args.db, args.older_than_days, apply=args.apply)
        print(json.dumps(result, indent=2))
if __name__=="__main__": main()
