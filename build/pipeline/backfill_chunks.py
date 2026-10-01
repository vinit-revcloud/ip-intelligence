"""Run the big proxycheck.io backfill in safe chunks, after the plan has been upgraded.

Each chunk is one top-up run of ipintel-proxycheck-daily limited to CHUNK addresses: it is sent, merged and
checked before the next chunk starts. The unified tables are refreshed after every REFRESH_EVERY chunks and at
the end, not after each chunk, which saves about 7 minutes per chunk.

Stops at once, and does nothing more, when:
  - a run fails or any of its checks fails;
  - a run adds no batches (the day's limit is reached, or every address is answered);
  - the pipeline is paused.

usage (from build/pipeline, AWS profile ipintel-builder):
  python backfill_chunks.py --chunk 250000 --max-chunks 1      # first, a test chunk
  python backfill_chunks.py --chunk 1000000                    # then the rest
"""
import argparse
import json
import time

import boto3
from boto3.dynamodb.conditions import Key

S = boto3.Session(profile_name="ipintel-builder", region_name="us-west-2")
LAM = S.client("lambda")
T = S.resource("dynamodb").Table("ipintel-pipeline-state")
FN = "ipintel-proxycheck-daily"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def runs_since(pk, since):
    return T.query(KeyConditionExpression=Key("pk").eq(pk) & Key("sk").gte(since))["Items"]


def wait_for(pk, since, timeout_s):
    """Wait until every run of pk started since `since` is finished; return them (oldest first)."""
    end = time.time() + timeout_s
    while time.time() < end:
        rs = runs_since(pk, since)
        if rs and all(r.get("status") not in ("running", "started") for r in rs):
            # a hand-over starts a new item; give it a moment to appear before deciding
            time.sleep(20)
            rs2 = runs_since(pk, since)
            if len(rs2) == len(rs) and all(r.get("status") not in ("running", "started") for r in rs2):
                return sorted(rs2, key=lambda r: r["sk"])
        time.sleep(30)
    raise SystemExit("Timed out waiting for %s" % pk)


def failed_checks(run):
    return [c.get("name") for c in (run.get("checks") or []) if isinstance(c, dict) and not c.get("passed", True)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=1000000)
    ap.add_argument("--max-chunks", type=int, default=20)
    ap.add_argument("--refresh-every", type=int, default=2)
    a = ap.parse_args()
    for i in range(1, a.max_chunks + 1):
        since = now()
        skip = (i % a.refresh_every) != 0
        LAM.invoke(FunctionName=FN, InvocationType="Event", Payload=json.dumps(
            {"trigger": "backfill-chunk-%d" % i, "topup": True, "max_addresses": a.chunk, "skip_publish": skip}).encode())
        print("%s chunk %d started (up to %d addresses, refresh unified: %s)" % (since, i, a.chunk, not skip), flush=True)
        runs = wait_for("run#" + FN.replace("ipintel-", ""), since, 4 * 3600)
        spent = sum(int(r.get("queries_spent") or 0) for r in runs)
        added = sum(int(r.get("topup_batches_added") or 0) for r in runs)
        bad = [r for r in runs if r.get("status") != "succeeded" or failed_checks(r)]
        print("%s chunk %d finished: %d runs, %d queries, %d batches added" % (now(), i, len(runs), spent, added), flush=True)
        if bad:
            for r in bad:
                print("  STOP: %s %s %s failed checks: %s" % (r["sk"], r.get("status"), r.get("message"), failed_checks(r)))
            return
        if not skip:
            pubs = wait_for("run#publish-unified", since, 3600)
            if any(p.get("status") != "succeeded" for p in pubs):
                print("  STOP: unified refresh failed:", [(p["sk"], p.get("status"), p.get("message")) for p in pubs])
                return
            print("  unified tables refreshed", flush=True)
        if added == 0:
            print("No more batches: the day's limit is reached or every address has an answer.")
            break
    # final refresh so the unified tables hold everything
    since = now()
    LAM.invoke(FunctionName=FN, InvocationType="Event", Payload=json.dumps({"action": "publish", "trigger": "backfill-final"}).encode())
    pubs = wait_for("run#publish-unified", since, 3600)
    print("final unified refresh:", [(p["sk"], p.get("status")) for p in pubs])


if __name__ == "__main__":
    main()
