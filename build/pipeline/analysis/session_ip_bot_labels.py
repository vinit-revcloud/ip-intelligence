"""One-time bot / not-bot labelling of every session IP (MoM rule), with the evidence behind each label.

Population: every public IP with a website session in unified.unified_session_summary between START and END
(90 to 7 days before the run date, so lead revenue has had time to appear).
Leads: sampledb.revenue_leads_plus joined on utm_content = session_id, lead created on or after the session.

Label (MoM, strict):
  real_person   at least one lead with expected_revenue > 0
  bot           everything else, split for review into
                  lead_no_revenue  a lead, but no revenue (blank counted as 0)
                  no_lead          no lead at all
Evidence per IP: sessions, bot-click sessions (session table), experiment ids, each vendor's proxy answer,
the resolved proxy verdict. Read only: nothing is written to any table.

usage (from build/pipeline, AWS profile ipintel-builder): python analysis/session_ip_bot_labels.py
Writes CSV/JSON to <project>/analysis/session-ip-bot-labels-2026-09/.
"""
import csv
import json
import os
import sys

os.environ.setdefault("AWS_PROFILE", "ipintel-builder")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import common as c  # noqa: E402

START, END = "2026-06-18", "2026-09-09"
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "analysis", "session-ip-bot-labels-2026-09"))
FLAG = "(coalesce(i.is_proxy,false) OR coalesce(i.is_vpn,false) OR coalesce(i.is_tor,false) OR coalesce(i.is_datacenter,false) " \
       "OR coalesce(i.is_bot,false) OR coalesce(i.is_compromised,false) OR coalesce(i.is_scraper,false))"
STAGE_RANK = "CASE lead_status_category WHEN 'closed' THEN 5 WHEN 'listing' THEN 4 WHEN 'meeting' THEN 3 " \
             "WHEN 'intro_qualified' THEN 2 WHEN 'below_intro' THEN 1 ELSE 0 END"
VENDORS = ["fraudlogix_tune", "ip2proxy_px12", "proxycheck_io"]

SQL = f"""
WITH s AS (
  SELECT session_id, session_ip AS ip, session_date, is_bot_click, nullif(experiment_id, '') AS experiment_id,
         lower(ip_is_proxy) AS sess_proxy
  FROM unified.unified_session_summary
  WHERE session_date BETWEEN date '{START}' AND date '{END}' AND nullif(session_ip, '') IS NOT NULL
    AND {c.public_ipv4_sql('session_ip')}),
l AS (SELECT id, utm_content, date_pst, expected_revenue, lead_status_category, {STAGE_RANK} AS stage_rank
      FROM sampledb.revenue_leads_plus WHERE date_pst >= date '{START}'),
sl AS (SELECT s.*, l.id AS lead_id, l.expected_revenue, l.lead_status_category, l.stage_rank
       FROM s LEFT JOIN l ON l.utm_content = s.session_id AND l.date_pst >= s.session_date),
per_ip AS (
  SELECT ip,
    count(DISTINCT session_id) AS sessions,
    count(DISTINCT CASE WHEN is_bot_click THEN session_id END) AS bot_click_sessions,
    count(DISTINCT CASE WHEN sess_proxy = 'true' THEN session_id END) AS session_proxy_sessions,
    array_join(array_sort(array_distinct(filter(array_agg(experiment_id), x -> x IS NOT NULL))), ' ') AS experiment_ids,
    min(session_date) AS first_session, max(session_date) AS last_session,
    count(DISTINCT lead_id) AS leads,
    round(sum(coalesce(expected_revenue, 0)), 2) AS revenue,
    max_by(lead_status_category, stage_rank) AS lead_category
  FROM sl GROUP BY ip),
v AS (
  SELECT i.ip_address,
    max(CASE WHEN i.vendor = 'fraudlogix_tune' AND i.is_proxy IS NOT NULL THEN CAST({FLAG} AS integer) END) AS fraudlogix_flag,
    max(CASE WHEN i.vendor = 'fraudlogix_tune' THEN CAST(i.is_bot AS integer) END) AS fraudlogix_bot,
    max(CASE WHEN i.vendor = 'ip2proxy_px12' AND i.is_proxy IS NOT NULL THEN CAST({FLAG} AS integer) END) AS ip2proxy_flag,
    max(CASE WHEN i.vendor = 'proxycheck_io' AND i.is_proxy IS NOT NULL THEN CAST({FLAG} AS integer) END) AS proxycheck_flag,
    max(CASE WHEN i.vendor = 'proxycheck_io' THEN CAST(i.is_vpn AS integer) END) AS proxycheck_vpn,
    max(CASE WHEN i.vendor = 'proxycheck_io' THEN i.isp END) AS isp
  FROM ipintel_curated.ip_intelligence i JOIN (SELECT DISTINCT ip FROM s) x ON x.ip = i.ip_address
  GROUP BY i.ip_address)
SELECT p.*,
  CASE WHEN p.revenue > 0 THEN 'real_person' ELSE 'bot' END AS label,
  CASE WHEN p.revenue > 0 THEN 'real_person' WHEN p.leads > 0 THEN 'lead_no_revenue' ELSE 'no_lead' END AS label_detail,
  v.fraudlogix_flag, v.fraudlogix_bot, v.ip2proxy_flag, v.proxycheck_flag, v.proxycheck_vpn, v.isp,
  a.risk_score AS proxycheck_risk,
  r.proxy_status, CAST(r.flagged AS integer) AS resolved_flagged,
  (v.fraudlogix_flag IS NOT NULL OR v.ip2proxy_flag IS NOT NULL OR v.proxycheck_flag IS NOT NULL) AS has_proxy_answer
FROM per_ip p
LEFT JOIN v ON v.ip_address = p.ip
LEFT JOIN ipintel_curated.ip_intelligence_analytics a ON a.ip_address = p.ip AND a.vendor = 'proxycheck_io'
LEFT JOIN ipintel_curated.ip_resolved r ON r.ip_address = p.ip
ORDER BY p.ip
"""


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def write_csv(name, data):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        if data:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    print("wrote %s (%d rows)" % (path, len(data)))


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = c.rows(SQL, timeout_s=900)
    direct = c.rows(f"""SELECT count(DISTINCT session_ip) AS ips, count(*) AS sessions FROM unified.unified_session_summary
        WHERE session_date BETWEEN date '{START}' AND date '{END}' AND nullif(session_ip, '') IS NOT NULL
          AND {c.public_ipv4_sql('session_ip')}""")[0]
    write_csv("session_ip_labels.csv", rows)

    n = len(rows)
    by = lambda k: {v: sum(1 for r in rows if r[k] == v) for v in sorted({r[k] for r in rows})}
    labels = by("label_detail")

    # Evidence for each label group
    groups = []
    for lab in ("real_person", "lead_no_revenue", "no_lead"):
        rs = [r for r in rows if r["label_detail"] == lab]
        g = {"label_detail": lab, "ips": len(rs),
             "with_proxy_answer": sum(1 for r in rs if r["has_proxy_answer"]),
             "bot_click_session_ips": sum(1 for r in rs if r["bot_click_sessions"] > 0),
             "resolved_flagged_ips": sum(1 for r in rs if r["resolved_flagged"] == 1),
             "fraudlogix_bot_ips": sum(1 for r in rs if r["fraudlogix_bot"] == 1),
             "proxycheck_high_risk_ips": sum(1 for r in rs if (r["proxycheck_risk"] or 0) >= 67),
             "in_experiment_ips": sum(1 for r in rs if r["experiment_ids"])}
        for k in list(g):
            if k.endswith("_ips") or k == "with_proxy_answer":
                g[k.replace("_ips", "") + "_pct" if k != "with_proxy_answer" else "with_proxy_answer_pct"] = pct(g[k], len(rs))
        groups.append(g)
    write_csv("label_evidence.csv", groups)

    # Vendor scorecard on every session IP (bot = positive class, strict label)
    card = []
    for vendor, col in (("fraudlogix_tune", "fraudlogix_flag"), ("ip2proxy_px12", "ip2proxy_flag"),
                        ("proxycheck_io", "proxycheck_flag"), ("session_summary_bot_click", None), ("resolved_answer", "resolved_flagged")):
        tp = fp = tn = fn = na = 0
        for r in rows:
            f = (1 if r["bot_click_sessions"] > 0 else 0) if col is None else r[col]
            if f is None:
                na += 1
                continue
            bot = r["label"] == "bot"
            if f and bot: tp += 1
            elif f and not bot: fp += 1
            elif not f and not bot: tn += 1
            else: fn += 1
        ans = tp + fp + tn + fn
        card.append({"source": vendor, "session_ips": n, "answered": ans, "coverage_pct": pct(ans, n), "flagged": tp + fp,
                     "TP": tp, "FP": fp, "TN": tn, "FN": fn, "no_answer": na, "FPR_pct": pct(fp, fp + tn),
                     "accuracy_pct": pct(tp + tn, ans), "precision_pct": pct(tp, tp + fp), "recall_pct": pct(tp, tp + fn)})
    write_csv("vendor_scorecard_all_session_ips.csv", card)

    # Per experiment
    exp = {}
    for r in rows:
        for e in (r["experiment_ids"] or "").split():
            d = exp.setdefault(e, {"experiment_id": e, "ips": 0, "real_person": 0, "lead_no_revenue": 0, "no_lead": 0,
                                   "bot_click_ips": 0, "resolved_flagged_ips": 0, "with_proxy_answer": 0})
            d["ips"] += 1
            d[r["label_detail"]] += 1
            d["bot_click_ips"] += 1 if r["bot_click_sessions"] > 0 else 0
            d["resolved_flagged_ips"] += 1 if r["resolved_flagged"] == 1 else 0
            d["with_proxy_answer"] += 1 if r["has_proxy_answer"] else 0
    exp_rows = sorted(exp.values(), key=lambda d: -d["ips"])
    for d in exp_rows:
        d["bot_pct_mom"] = pct(d["lead_no_revenue"] + d["no_lead"], d["ips"])
        d["flagged_pct"] = pct(d["resolved_flagged_ips"], d["ips"])
        d["proxy_answer_pct"] = pct(d["with_proxy_answer"], d["ips"])
    write_csv("per_experiment.csv", exp_rows)

    checks = {
        "IPs equal a direct count": n == direct["ips"],
        "sessions equal a direct count": sum(r["sessions"] for r in rows) == direct["sessions"],
        "every IP has one label": all(r["label"] in ("real_person", "bot") for r in rows),
        "real_person exactly when revenue > 0": all((r["revenue"] > 0) == (r["label"] == "real_person") for r in rows),
        "scorecard adds up": all(x["TP"] + x["FP"] + x["TN"] + x["FN"] + x["no_answer"] == n for x in card),
    }
    summary = {"window": [START, END], "session_ips": n, "sessions": direct["sessions"], "labels": labels,
               "bot_mom": labels.get("lead_no_revenue", 0) + labels.get("no_lead", 0),
               "with_proxy_answer": sum(1 for r in rows if r["has_proxy_answer"]),
               "with_proxycheck": sum(1 for r in rows if r["proxycheck_flag"] is not None),
               "evidence": groups, "scorecard": card, "experiments": len(exp_rows), "checks": checks}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, default=str)
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
