"""Build the data snapshot the Lovable app shows (our API is retired, so the app reads these files).

Reads the two one-time analyses (analysis/lead-ip-vendor-2026-09, analysis/session-ip-bot-labels-2026-09), the two
report files the daily jobs write to S3, and every vendor's answer for the lead IPs. Read only.

Writes <project>/app-data/*.json. Copy that folder into the Lovable project as public/data/.
usage (from build/pipeline, AWS profile ipintel-builder): python analysis/export_app_data.py
"""
import csv
import datetime
import json
import os
import sys

os.environ.setdefault("AWS_PROFILE", "ipintel-builder")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import common as c  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LEAD = os.path.join(ROOT, "analysis", "lead-ip-vendor-2026-09")
SESS = os.path.join(ROOT, "analysis", "session-ip-bot-labels-2026-09")
VERD = os.path.join(ROOT, "analysis", "session-ip-bot-verdict-2026-09")
OUT = os.path.join(ROOT, "app-data")


TEXT_COLS = {"ip", "experiment_id", "experiment_ids", "asn", "zip_code"}   # ids that look like numbers stay text


def read_csv(path):
    def conv(v):
        if v in ("", "None"):
            return None
        if v in ("True", "False"):
            return v == "True"
        try:
            f = float(v)
            return int(f) if f.is_integer() and "." not in v else f
        except ValueError:
            return v
    with open(path, encoding="utf-8") as f:
        return [{k: (v or None) if k in TEXT_COLS else conv(v) for k, v in r.items()} for r in csv.DictReader(f)]


def dump(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)
    print("wrote %s (%d KB)" % (path, os.path.getsize(path) // 1024))


def verdict_block():
    """The bot verdict analysis (session_ip_bot_verdict.py), or None if it has not been run."""
    path = os.path.join(VERD, "summary.json")
    if not os.path.exists(path):
        return None
    v = json.load(open(path, encoding="utf-8"))
    return {"window": v["window"], "session_ips": v["session_ips"], "paying_ips": v["paying_ips"],
            "max_fpr_pct": v["max_fpr_pct"], "strong_signals": v["strong_signals"], "weak_signals": v["weak_signals"],
            "verdicts": v["verdicts"], "verdict_pct": v["verdict_pct"],
            "combined_rule_fpr_on_paying_pct": v["combined_rule_fpr_on_paying_pct"],
            "signal_test": v["signal_test"], "by_mom_label": v["by_mom_label"], "bot_reasons": v["bot_reasons"],
            "per_experiment": read_csv(os.path.join(VERD, "verdict_per_experiment.csv"))}


def main():
    os.makedirs(OUT, exist_ok=True)
    now = c.now_iso()
    lead_sum = json.load(open(os.path.join(LEAD, "summary.json"), encoding="utf-8"))
    sess_sum = json.load(open(os.path.join(SESS, "summary.json"), encoding="utf-8"))
    labels = read_csv(os.path.join(LEAD, "ip_labels.csv"))
    ips = [r["ip"] for r in labels]

    # Every vendor's answer for the lead IPs: risk and location.
    inl = ", ".join(c.lit(i) for i in ips)
    intel = c.rows(f"""SELECT ip_address, vendor, is_proxy, is_vpn, is_tor, is_datacenter, is_bot, is_compromised,
                              is_scraper, is_anonymous, isp, asn, updated_at
                       FROM ipintel_curated.ip_intelligence WHERE ip_address IN ({inl})""", timeout_s=600)
    geo = c.rows(f"""SELECT ip_address, vendor, state, city, zip_code, latitude, longitude, timezone, updated_at
                     FROM ipintel_curated.ip_geo WHERE ip_address IN ({inl})""", timeout_s=600)
    res = c.rows(f"""SELECT ip_address, geo_status, state, city, zip_code, geo_decided_by, proxy_status, flagged,
                            proxy_decided_by, isp, proxycheck_risk_score
                     FROM ipintel_curated.ip_resolved WHERE ip_address IN ({inl})""", timeout_s=600)
    sess = {r["ip"]: r for r in read_csv(os.path.join(SESS, "session_ip_labels.csv")) if r["ip"] in set(ips)}
    by_ip = {}
    for r in labels:
        s = sess.get(r["ip"]) or {}
        by_ip[r["ip"]] = {"ip": r["ip"], "label": r["label"], "revenue": r["revenue"], "leads": r["leads"],
                          "blank_revenue_leads": r["blank_revenue_leads"], "lead_category": r["lead_category"],
                          "furthest_stage": r["furthest_stage"], "sessions": r["sessions"],
                          "bot_click_sessions": r["bot_click_sessions"], "experiment_ids": s.get("experiment_ids"),
                          "risk": {}, "geo": {}, "resolved": None}
    for x in intel:
        by_ip[x.pop("ip_address")]["risk"][x.pop("vendor")] = x
    for x in geo:
        by_ip[x.pop("ip_address")]["geo"][x.pop("vendor")] = x
    for x in res:
        by_ip[x.pop("ip_address")]["resolved"] = x
    outcomes = {}
    for v in ("fraudlogix_tune", "ip2proxy_px12", "proxycheck_io", "session_summary"):
        for r in read_csv(os.path.join(LEAD, "ips_%s.csv" % v)):
            by_ip[r["ip"]].setdefault("outcome", {})[v] = r["outcome"]
            if v == "session_summary":
                by_ip[r["ip"]]["risk"]["session_summary"] = {"flagged": r["flagged"], "is_proxy": r["is_proxy"],
                                                             "is_bot": r["is_bot"]}
            if v == "fraudlogix_tune" and r["fraud_reason"]:
                by_ip[r["ip"]]["risk"].setdefault("fraudlogix_tune", {})["fraud_reason"] = r["fraud_reason"]
            if v == "proxycheck_io" and r["risk_score"] is not None:
                by_ip[r["ip"]]["risk"].setdefault("proxycheck_io", {})["risk_score"] = r["risk_score"]
        outcomes[v] = True

    dump("lead_ips.json", {"as_of": now, "window": lead_sum["window"], "rows": list(by_ip.values())})
    dump("lead_ip_analysis.json", {
        "as_of": now, "window": lead_sum["window"], "lead_ips": lead_sum["lead_ips"], "leads": lead_sum["leads"],
        "real_person_ips": lead_sum["real_person_ips"], "bot_ips": lead_sum["bot_ips"],
        "blank_revenue_ips": lead_sum["blank_revenue_ips"],
        "scorecard_any_flag": read_csv(os.path.join(LEAD, "scorecard_any_flag.csv")),
        "scorecard_bot_flag_only": read_csv(os.path.join(LEAD, "scorecard_bot_flag_only.csv")),
        "lead_category_signal": read_csv(os.path.join(LEAD, "lead_category_signal.csv")),
        "lead_stage_signal": read_csv(os.path.join(LEAD, "lead_stage_signal.csv")),
        "fraudlogix_wrong_flags": [{k: r[k] for k in ("ip", "revenue", "lead_category", "furthest_stage", "fraud_reason",
                                                      "is_proxy", "is_vpn", "is_bot")}
                                   for r in read_csv(os.path.join(LEAD, "fraudlogix_wrong_flags.csv"))],
        "fraudlogix_wrong_by_reason": lead_sum["fraudlogix_wrong_by_reason"]})
    dump("session_ip_labels.json", {
        "as_of": now, "window": sess_sum["window"], "session_ips": sess_sum["session_ips"],
        "sessions": sess_sum["sessions"], "labels": sess_sum["labels"], "bot_mom": sess_sum["bot_mom"],
        "with_proxy_answer": sess_sum["with_proxy_answer"], "with_proxycheck": sess_sum["with_proxycheck"],
        "evidence": sess_sum["evidence"], "scorecard": sess_sum["scorecard"],
        "per_experiment": read_csv(os.path.join(SESS, "per_experiment.csv")),
        "verdict": verdict_block()})
    for key, name in (("enrichment_coverage.json", "coverage.json"), ("geo_accuracy.json", "geo_accuracy.json")):
        dump(name, c.s3_get_json("%s/serving/ipintel_curated/%s" % (c.PREFIX, key)))
    cov = c.rows("""WITH ans AS (SELECT ip_address, count_if(is_proxy IS NOT NULL) n, count_if(vendor = 'proxycheck_io') pc
                                 FROM ipintel_curated.ip_intelligence GROUP BY 1)
                    SELECT count(*) AS addresses, count_if(n > 0) AS with_proxy_answer, count_if(pc > 0) AS with_proxycheck FROM ans""")[0]
    comp = c.s3_get_json("%s/serving/ipintel_curated/table_completeness.json" % c.PREFIX)
    dump("proxy_coverage.json", {"as_of": now, **cov, "completeness": comp})
    for t in ("vendor_overview_geo", "vendor_overview_proxy"):
        dump(t + ".json", {"as_of": now, "table": "unified." + t,
                           "rows": c.rows("SELECT * FROM ipintel_curated.%s ORDER BY vendor" % t)})
    dump("manifest.json", {"as_of": now, "files": sorted(os.listdir(OUT))})


if __name__ == "__main__":
    main()
