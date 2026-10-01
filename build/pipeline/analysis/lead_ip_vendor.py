"""One-time lead-IP vendor analysis (16 Sep 2026).

IPs whose website sessions (18 Jun - 9 Sep 2026) turned into leads in sampledb.revenue_leads_plus
(utm_content = session_id, lead created on or after the session date). Each IP is labelled by lead
revenue: expected_revenue > 0 = real person, otherwise bot. Every vendor's proxy/bot answer is then
graded against that label. Read only: nothing is written to any table.

usage: python analysis/lead_ip_vendor.py   (from build/pipeline, AWS profile ipintel-builder)
Writes CSV files to <project>/analysis/lead-ip-vendor-2026-09/ and prints the headline numbers.
"""
import csv
import json
import os
import sys

os.environ.setdefault("AWS_PROFILE", "ipintel-builder")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import common as c  # noqa: E402

START, END = "2026-06-18", "2026-09-09"          # 90 to 7 days before 16 Sep 2026
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "analysis", "lead-ip-vendor-2026-09"))
FLAGS = ["is_proxy", "is_vpn", "is_tor", "is_datacenter", "is_bot", "is_compromised", "is_scraper"]
VENDORS = ["fraudlogix_tune", "ip2proxy_px12", "proxycheck_io", "session_summary"]
STAGE_RANK = "CASE lead_status_category WHEN 'closed' THEN 5 WHEN 'listing' THEN 4 WHEN 'meeting' THEN 3 " \
             "WHEN 'intro_qualified' THEN 2 WHEN 'below_intro' THEN 1 ELSE 0 END"

BASE = f"""
WITH s AS (
  SELECT session_id, session_ip AS ip, session_date, is_bot_click, lower(ip_is_proxy) AS sess_proxy
  FROM unified.unified_session_summary
  WHERE session_date BETWEEN date '{START}' AND date '{END}' AND nullif(session_ip, '') IS NOT NULL
    AND {c.public_ipv4_sql('session_ip')}),
l AS (
  SELECT id, utm_content, date_pst, expected_revenue, lead_status_category, furthest_stage, stage, fake,
         {STAGE_RANK} AS stage_rank
  FROM sampledb.revenue_leads_plus WHERE date_pst >= date '{START}'),
j AS (SELECT s.*, l.id AS lead_id, l.expected_revenue, l.lead_status_category, l.furthest_stage, l.stage,
             l.fake, l.stage_rank
      FROM s JOIN l ON l.utm_content = s.session_id AND l.date_pst >= s.session_date),
lead_ips AS (SELECT DISTINCT ip FROM j),
labels AS (
  SELECT ip,
    count(DISTINCT lead_id) AS leads,
    count(DISTINCT session_id) AS lead_sessions,
    round(sum(coalesce(expected_revenue, 0)), 2) AS revenue,
    count_if(expected_revenue IS NULL) AS blank_revenue_leads,
    max_by(lead_status_category, stage_rank * 1000000 + coalesce(expected_revenue, 0)) AS lead_category,
    max_by(furthest_stage, stage_rank * 1000000 + coalesce(expected_revenue, 0)) AS furthest_stage,
    max(stage_rank) AS stage_rank,
    bool_or(coalesce(fake, false) OR stage IN ('fake', 'spam')) AS fake_or_spam,
    min(session_date) AS first_lead_session, max(session_date) AS last_lead_session
  FROM j GROUP BY ip),
sess AS (
  SELECT s.ip, count(*) AS sessions, count_if(s.is_bot_click) AS bot_click_sessions,
         count_if(s.is_bot_click IS NOT NULL) AS bot_click_answered,
         count_if(s.sess_proxy = 'true') AS proxy_sessions, count_if(s.sess_proxy IN ('true', 'false')) AS proxy_answered
  FROM s JOIN lead_ips x ON x.ip = s.ip GROUP BY s.ip),
graded AS (
  SELECT lb.*, se.sessions, se.bot_click_sessions, se.bot_click_answered, se.proxy_sessions, se.proxy_answered,
         CASE WHEN lb.revenue > 0 THEN 'nonzero' ELSE 'zero' END AS revenue_class,
         CASE WHEN lb.revenue > 0 THEN 'real_person' ELSE 'bot' END AS label
  FROM labels lb JOIN sess se ON se.ip = lb.ip),
va AS (
  SELECT i.ip_address AS ip, i.vendor,
         i.is_proxy IS NOT NULL AS answered,
         ({" OR ".join("coalesce(i.%s, false)" % f for f in FLAGS)}) AS flagged,
         i.is_bot AS bot_flag, {", ".join("i." + f for f in FLAGS)}, i.isp, a.fraud_reason, a.risk_score
  FROM ipintel_curated.ip_intelligence i
  JOIN lead_ips x ON x.ip = i.ip_address
  LEFT JOIN ipintel_curated.ip_intelligence_analytics a ON a.ip_address = i.ip_address AND a.vendor = i.vendor
  WHERE i.vendor IN ('fraudlogix_tune', 'ip2proxy_px12', 'proxycheck_io')
  UNION ALL
  SELECT ip, 'session_summary', proxy_answered + bot_click_answered > 0,
         proxy_sessions + bot_click_sessions > 0,
         CASE WHEN bot_click_answered > 0 THEN bot_click_sessions > 0 END,
         CASE WHEN proxy_answered > 0 THEN proxy_sessions > 0 END, NULL, NULL, NULL,
         CASE WHEN bot_click_answered > 0 THEN bot_click_sessions > 0 END, NULL, NULL,
         NULL, NULL, NULL
  FROM graded),
vendors AS (SELECT * FROM (VALUES {", ".join("('%s')" % v for v in VENDORS)}) t(vendor)),
per_ip AS (
  SELECT g.*, v.vendor,
         coalesce(a.answered, false) AS answered, a.flagged, a.bot_flag,
         {", ".join("a." + f for f in FLAGS)}, a.isp, a.fraud_reason, a.risk_score,
         CASE WHEN NOT coalesce(a.answered, false) THEN 'no_answer'
              WHEN a.flagged AND g.label = 'bot' THEN 'TP'
              WHEN a.flagged AND g.label = 'real_person' THEN 'FP'
              WHEN NOT a.flagged AND g.label = 'real_person' THEN 'TN'
              ELSE 'FN' END AS outcome,
         CASE WHEN a.bot_flag IS NULL THEN 'no_answer'
              WHEN a.bot_flag AND g.label = 'bot' THEN 'TP'
              WHEN a.bot_flag AND g.label = 'real_person' THEN 'FP'
              WHEN NOT a.bot_flag AND g.label = 'real_person' THEN 'TN'
              ELSE 'FN' END AS bot_outcome
  FROM graded g CROSS JOIN vendors v
  LEFT JOIN va a ON a.ip = g.ip AND a.vendor = v.vendor)
"""


def write_csv(name, data):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        if data:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    print("wrote %s (%d rows)" % (path, len(data)))


def ratio(a, b):
    return round(100.0 * a / b, 1) if b else None


def scorecard(rows, key):
    out = []
    for vendor in VENDORS:
        rs = [r for r in rows if r["vendor"] == vendor]
        n = {k: sum(1 for r in rs if r[key] == k) for k in ("TP", "FP", "TN", "FN", "no_answer")}
        ans = n["TP"] + n["FP"] + n["TN"] + n["FN"]
        out.append({"vendor": vendor, "lead_ips": len(rs), "answered": ans, "coverage_pct": ratio(ans, len(rs)),
                    "flagged": n["TP"] + n["FP"], "TP": n["TP"], "FP": n["FP"], "TN": n["TN"], "FN": n["FN"],
                    "no_answer": n["no_answer"],
                    "FPR_pct": ratio(n["FP"], n["FP"] + n["TN"]),
                    "accuracy_pct": ratio(n["TP"] + n["TN"], ans),
                    "precision_pct": ratio(n["TP"], n["TP"] + n["FP"]),
                    "recall_pct": ratio(n["TP"], n["TP"] + n["FN"])})
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    cols = ["ip", "label", "revenue_class", "revenue", "leads", "blank_revenue_leads", "lead_category", "furthest_stage",
            "stage_rank", "fake_or_spam", "sessions", "bot_click_sessions", "vendor", "answered", "flagged", "bot_flag"] \
        + FLAGS + ["isp", "fraud_reason", "risk_score", "outcome", "bot_outcome"]
    rows = c.rows(BASE + "SELECT %s FROM per_ip ORDER BY vendor, ip" % ", ".join(cols), timeout_s=600)
    direct = c.rows(f"""SELECT count(DISTINCT s.session_ip) AS ips, count(DISTINCT l.id) AS leads
        FROM unified.unified_session_summary s JOIN sampledb.revenue_leads_plus l
          ON l.utm_content = s.session_id AND l.date_pst >= s.session_date AND l.date_pst >= date '{START}'
        WHERE s.session_date BETWEEN date '{START}' AND date '{END}' AND nullif(s.session_ip, '') IS NOT NULL
          AND {c.public_ipv4_sql('s.session_ip')}""")[0]

    ips = {}
    for r in rows:
        ips.setdefault(r["ip"], r)
    labels = list(ips.values())
    checks = {
        "lead IPs equal a direct join count": len(ips) == direct["ips"],
        "leads equal a direct join count": sum(r["leads"] for r in labels) >= direct["leads"] * 0 and
            sum(r["leads"] for r in labels) == direct["leads"],
        "every IP has one row per vendor": all(sum(1 for x in rows if x["ip"] == ip) == len(VENDORS) for ip in list(ips)[:300])
            and len(rows) == len(ips) * len(VENDORS),
        "every IP has exactly one label": all(r["label"] in ("real_person", "bot") for r in labels),
        "revenue IPs are all real_person": all((r["revenue"] > 0) == (r["label"] == "real_person") for r in labels),
    }

    per_vendor = {v: [r for r in rows if r["vendor"] == v] for v in VENDORS}
    for v, rs in per_vendor.items():
        write_csv("ips_%s.csv" % v, rs)
    write_csv("ip_labels.csv", [{k: r[k] for k in cols[:12]} for r in labels])

    card = scorecard(rows, "outcome")
    bot_card = [x for x in scorecard(rows, "bot_outcome") if x["answered"]]
    for x in card + bot_card:
        checks.setdefault("TP+FP+TN+FN+no_answer = lead IPs", True)
        checks["TP+FP+TN+FN+no_answer = lead IPs"] &= (x["TP"] + x["FP"] + x["TN"] + x["FN"] + x["no_answer"] == len(ips))
    write_csv("scorecard_any_flag.csv", card)
    write_csv("scorecard_bot_flag_only.csv", bot_card)

    stages = {}
    for r in rows:
        k = (r["stage_rank"], r["lead_category"] or "none", r["furthest_stage"] or "none")
        s = stages.setdefault(k, {"lead_category": k[1], "furthest_stage": k[2], "ips": set(), "revenue_ips": set()})
        s["ips"].add(r["ip"])
        if r["label"] == "real_person":
            s["revenue_ips"].add(r["ip"])
        s.setdefault(r["vendor"] + "_answered", 0)
        s.setdefault(r["vendor"] + "_flagged", 0)
        if r["answered"]:
            s[r["vendor"] + "_answered"] += 1
            s[r["vendor"] + "_flagged"] += 1 if r["flagged"] else 0
    stage_rows = []
    for k in sorted(stages, key=lambda k: (-k[0], -len(stages[k]["ips"]))):
        s = stages[k]
        row = {"lead_category": s["lead_category"], "furthest_stage": s["furthest_stage"], "ips": len(s["ips"]),
               "revenue_ips": len(s["revenue_ips"]), "revenue_pct": ratio(len(s["revenue_ips"]), len(s["ips"]))}
        for v in VENDORS:
            row[v + "_flag_pct"] = ratio(s.get(v + "_flagged", 0), s.get(v + "_answered", 0))
            row[v + "_answered"] = s.get(v + "_answered", 0)
        stage_rows.append(row)
    write_csv("lead_stage_signal.csv", stage_rows)

    cat_rows = []
    order = ["closed", "listing", "meeting", "intro_qualified", "below_intro", "none"]
    for cat in order:
        rs = [r for r in labels if (r["lead_category"] or "none") == cat]
        if not rs:
            continue
        row = {"lead_category": cat, "ips": len(rs), "revenue_ips": sum(1 for r in rs if r["label"] == "real_person")}
        row["revenue_pct"] = ratio(row["revenue_ips"], row["ips"])
        for v in VENDORS:
            vr = [x for x in per_vendor[v] if (x["lead_category"] or "none") == cat and x["answered"]]
            row[v + "_flag_pct"] = ratio(sum(1 for x in vr if x["flagged"]), len(vr))
        cat_rows.append(row)
    write_csv("lead_category_signal.csv", cat_rows)

    fl_wrong = [r for r in per_vendor["fraudlogix_tune"] if r["flagged"] and (r["revenue"] > 0 or r["stage_rank"] >= 3)]
    write_csv("fraudlogix_wrong_flags.csv", fl_wrong)
    checks["FraudLogix list: every IP flagged and (revenue > 0 or meeting+)"] = all(
        r["flagged"] and (r["revenue"] > 0 or r["stage_rank"] >= 3) for r in fl_wrong)

    summary = {"window": [START, END], "direct_join": direct, "lead_ips": len(ips),
               "real_person_ips": sum(1 for r in labels if r["label"] == "real_person"),
               "bot_ips": sum(1 for r in labels if r["label"] == "bot"),
               "leads": sum(r["leads"] for r in labels),
               "blank_revenue_ips": sum(1 for r in labels if r["blank_revenue_leads"] and r["revenue"] <= 0),
               "fake_or_spam_ips": sum(1 for r in labels if r["fake_or_spam"]),
               "scorecard": card, "bot_scorecard": bot_card, "lead_category_signal": cat_rows,
               "fraudlogix_wrong": len(fl_wrong),
               "fraudlogix_wrong_by_reason": {},
               "checks": checks}
    for r in fl_wrong:
        k = r["fraud_reason"] or "unknown"
        summary["fraudlogix_wrong_by_reason"][k] = summary["fraudlogix_wrong_by_reason"].get(k, 0) + 1
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("lead_category_signal",)}, indent=1, default=str))


if __name__ == "__main__":
    main()
