"""One-time bot verdict for every session IP: vendor network signals + session behaviour, tested against revenue.

Population and leads are the same as session_ip_bot_labels.py (MoM window, utm_content = session_id).

Proof of a human (from the leads table, not the session table's funnel fields, which are inflated):
  revenue > 0, or a lead that reached intro_qualified or later (no IP below that stage ever had revenue).

Candidate bot signals, per IP:
  ua_botlike        a session with an automation / crawler browser agent
  fraudlogix_bot    FraudLogix reason BOT_GENERATED / NON_HUMAN_SCRIPT
  datacenter        any vendor says datacenter / hosting
  tor, compromised  any vendor says so
  velocity          many sessions from the IP on one day (threshold chosen from the data)
  bot_click_all     every session is a bot click (session table)
  bounce_repeat     3+ sessions, all 0 seconds and 1 event, no engagement
  tz_mismatch       browser time zone offset differs from the IP's, in every session with both
  vpn_proxy         any vendor says VPN or proxy
A signal is STRONG only if
  - it fires on at most MAX_FPR of the paying IPs (known humans),
  - it fires more often on no-lead IPs than on paying IPs (so it points away from humans, not just at shared networks),
  - and it can be tested at all: a signal that requires "no engagement" can never fire on a paying IP, so it stays WEAK.
Engaged = a partial lead, or 3+ events over 5+ seconds. has_consent and has_quiz_start alone are not used: consent is
recorded on page load (40,771 consent sessions are 0 seconds / 1 event) and quiz start alone looks the same.

Verdict per IP (first match):
  human          proof of a human
  bot            a strong signal
  likely_human   engaged and no weak signal besides vpn_proxy / tz_mismatch
  suspicious     a weak signal
  unknown        nothing either way (typically a single bounce visit on a clean network)

Read only: nothing is written to any table.
usage (from build/pipeline, AWS profile ipintel-builder): python analysis/session_ip_bot_verdict.py
Writes to <project>/analysis/session-ip-bot-verdict-2026-09/.
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
MAX_FPR = 2.0                       # percent of paying IPs a strong signal may hit
VELOCITY_CANDIDATES = [5, 10, 20, 50, 100]
UNTESTABLE = {"bounce_repeat"}      # defined by "no engagement", so a paying IP can never match it
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "analysis", "session-ip-bot-verdict-2026-09"))
STAGE_RANK = "CASE lead_status_category WHEN 'closed' THEN 5 WHEN 'listing' THEN 4 WHEN 'meeting' THEN 3 " \
             "WHEN 'intro_qualified' THEN 2 WHEN 'below_intro' THEN 1 ELSE 0 END"
UA_BOT = "bot|crawl|spider|headless|phantom|selenium|puppeteer|playwright|python|curl|wget|httpclient|java/|go-http|scrapy|lighthouse|preview"

SQL = f"""
WITH s AS (
  SELECT session_id, session_ip AS ip, session_date, duration_seconds AS dur, event_count AS ev, is_bot_click,
         nullif(experiment_id, '') AS experiment_id, nullif(browser_agent, '') AS ua,
         regexp_like(lower(coalesce(browser_agent, '')), '{UA_BOT}') AS ua_botlike,
         (has_partial_lead = 'on' OR (coalesce(event_count, 0) >= 3 AND coalesce(duration_seconds, 0) >= 5)) AS engaged,
         CASE WHEN timezone IN ({{TZ_OK}}) THEN format_datetime(from_unixtime(to_unixtime(CAST(session_date AS timestamp)) + 43200, timezone), 'ZZ') END AS tz_browser,
         CASE WHEN ip_time_zone LIKE 'UTC%' THEN substr(ip_time_zone, 4) END AS tz_ip
  FROM unified.unified_session_summary
  WHERE session_date BETWEEN date '{START}' AND date '{END}' AND nullif(session_ip, '') IS NOT NULL
    AND {c.public_ipv4_sql('session_ip')}),
l AS (SELECT utm_content, date_pst, expected_revenue, {STAGE_RANK} AS stage_rank, id
      FROM sampledb.revenue_leads_plus WHERE date_pst >= date '{START}'),
sl AS (SELECT s.session_id, s.ip, l.id AS lead_id, l.expected_revenue, l.stage_rank
       FROM s JOIN l ON l.utm_content = s.session_id AND l.date_pst >= s.session_date),
lead_ip AS (SELECT ip, count(DISTINCT lead_id) AS leads, round(sum(coalesce(expected_revenue, 0)), 2) AS revenue,
                   max(stage_rank) AS stage_rank FROM sl GROUP BY ip),
per_day AS (SELECT ip, session_date, count(*) AS n FROM s GROUP BY 1, 2),
per_ip AS (
  SELECT ip,
    count(*) AS sessions,
    count(DISTINCT session_date) AS active_days,
    count(DISTINCT ua) AS user_agents,
    count_if(is_bot_click) AS bot_click_sessions,
    count_if(ua_botlike) AS ua_botlike_sessions,
    count_if(engaged) AS engaged_sessions,
    count_if(coalesce(dur, 0) = 0 AND coalesce(ev, 0) <= 1) AS bounce_sessions,
    count_if(tz_browser IS NOT NULL AND tz_ip IS NOT NULL) AS tz_known_sessions,
    count_if(tz_browser IS NOT NULL AND tz_ip IS NOT NULL AND tz_browser <> tz_ip) AS tz_mismatch_sessions,
    array_join(array_sort(array_distinct(filter(array_agg(experiment_id), x -> x IS NOT NULL))), ' ') AS experiment_ids
  FROM s GROUP BY ip),
v AS (
  SELECT i.ip_address,
    bool_or(i.vendor = 'fraudlogix_tune' AND coalesce(i.is_bot, false)) AS fraudlogix_bot,
    bool_or(coalesce(i.is_datacenter, false)) AS datacenter,
    bool_or(coalesce(i.is_tor, false)) AS tor,
    bool_or(coalesce(i.is_compromised, false)) AS compromised,
    bool_or(coalesce(i.is_vpn, false) OR coalesce(i.is_proxy, false)) AS vpn_proxy,
    bool_or(i.is_proxy IS NOT NULL) AS has_vendor_answer
  FROM ipintel_curated.ip_intelligence i JOIN (SELECT DISTINCT ip FROM s) x ON x.ip = i.ip_address
  GROUP BY i.ip_address)
SELECT p.*, d.max_sessions_day,
  coalesce(li.leads, 0) AS leads, coalesce(li.revenue, 0) AS revenue, coalesce(li.stage_rank, 0) AS stage_rank,
  coalesce(v.fraudlogix_bot, false) AS fraudlogix_bot, coalesce(v.datacenter, false) AS datacenter,
  coalesce(v.tor, false) AS tor, coalesce(v.compromised, false) AS compromised,
  coalesce(v.vpn_proxy, false) AS vpn_proxy, coalesce(v.has_vendor_answer, false) AS has_vendor_answer,
  a.risk_score AS proxycheck_risk
FROM per_ip p
JOIN (SELECT ip, max(n) AS max_sessions_day FROM per_day GROUP BY ip) d ON d.ip = p.ip
LEFT JOIN lead_ip li ON li.ip = p.ip
LEFT JOIN v ON v.ip_address = p.ip
LEFT JOIN ipintel_curated.ip_intelligence_analytics a ON a.ip_address = p.ip AND a.vendor = 'proxycheck_io'
ORDER BY p.ip
"""


def pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def write_csv(name, data):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        if data:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    print("wrote %s (%d rows)" % (path, len(data)))


def signals(r, velocity):
    """Every candidate bot signal for one IP."""
    return {
        "ua_botlike": r["ua_botlike_sessions"] > 0,
        "fraudlogix_bot": bool(r["fraudlogix_bot"]),
        "datacenter": bool(r["datacenter"]),
        "tor": bool(r["tor"]),
        "compromised": bool(r["compromised"]),
        "velocity": r["max_sessions_day"] >= velocity,
        "bot_click_all": r["bot_click_sessions"] == r["sessions"],
        "bounce_repeat": r["sessions"] >= 3 and r["bounce_sessions"] == r["sessions"] and r["engaged_sessions"] == 0,
        "tz_mismatch": r["tz_known_sessions"] > 0 and r["tz_mismatch_sessions"] == r["tz_known_sessions"],
        "vpn_proxy": bool(r["vpn_proxy"]),
    }


def valid_time_zones():
    """Browser time-zone names Athena can convert (it rejects names such as Etc/Unknown, and try() does not catch it)."""
    from zoneinfo import ZoneInfo
    names = [r["timezone"] for r in c.rows(f"""SELECT DISTINCT timezone FROM unified.unified_session_summary
        WHERE session_date BETWEEN date '{START}' AND date '{END}' AND nullif(timezone, '') IS NOT NULL""")]
    ok = []
    for z in names:
        try:
            if "/" in z and not z.startswith("Etc/"):
                ZoneInfo(z)
                ok.append(z)
        except Exception:
            pass
    return ok or ["-"]


def main():
    os.makedirs(OUT, exist_ok=True)
    tz_ok = valid_time_zones()
    print("time zones usable: %d" % len(tz_ok))
    rows = c.rows(SQL.replace("{TZ_OK}", ", ".join(c.lit(z) for z in tz_ok)), timeout_s=900)
    direct = c.rows(f"""SELECT count(DISTINCT session_ip) AS ips, count(*) AS sessions FROM unified.unified_session_summary
        WHERE session_date BETWEEN date '{START}' AND date '{END}' AND nullif(session_ip, '') IS NOT NULL
          AND {c.public_ipv4_sql('session_ip')}""")[0]
    n = len(rows)
    for r in rows:
        r["paying"] = r["revenue"] > 0
        r["human_proof"] = r["paying"] or r["stage_rank"] >= 2
        r["no_lead"] = r["leads"] == 0
    paying = [r for r in rows if r["paying"]]
    no_lead = [r for r in rows if r["no_lead"]]

    # Velocity threshold: the smallest candidate that stays within MAX_FPR on paying IPs.
    velocity = next((t for t in VELOCITY_CANDIDATES
                     if pct(sum(1 for r in paying if r["max_sessions_day"] >= t), len(paying)) <= MAX_FPR),
                    VELOCITY_CANDIDATES[-1])

    # Test every signal against the known humans.
    names = list(signals(rows[0], velocity))
    test = []
    for s in names:
        hit_pay = sum(1 for r in paying if signals(r, velocity)[s])
        hit_nolead = sum(1 for r in no_lead if signals(r, velocity)[s])
        hit_all = sum(1 for r in rows if signals(r, velocity)[s])
        fpr = pct(hit_pay, len(paying))
        nl = pct(hit_nolead, len(no_lead))
        testable = s not in UNTESTABLE
        ok = testable and hit_all > 0 and fpr <= MAX_FPR and nl > fpr
        test.append({"signal": s, "ips_hit": hit_all, "paying_hit": hit_pay, "paying_ips": len(paying),
                     "FPR_pct": fpr, "no_lead_hit": hit_nolead, "no_lead_hit_pct": pct(hit_nolead, len(no_lead)),
                     "testable": testable, "points_away_from_humans": nl > fpr,
                     "strength": "strong" if ok else "weak"})
    strong = [t["signal"] for t in test if t["strength"] == "strong"]
    weak = [t["signal"] for t in test if t["strength"] == "weak"]
    soft = {"vpn_proxy", "tz_mismatch"}          # common among real customers; never block "likely human"
    write_csv("signal_test.csv", test)

    out = []
    for r in rows:
        sg = signals(r, velocity)
        fired_strong = [s for s in strong if sg[s]]
        fired_weak = [s for s in weak if sg[s]]
        if r["human_proof"]:
            verdict = "human"
        elif fired_strong:
            verdict = "bot"
        elif r["engaged_sessions"] > 0 and not [s for s in fired_weak if s not in soft]:
            verdict = "likely_human"
        elif fired_weak:
            verdict = "suspicious"
        else:
            verdict = "unknown"
        out.append({"ip": r["ip"], "verdict": verdict, "strong_signals": " ".join(fired_strong),
                    "weak_signals": " ".join(fired_weak), "revenue": r["revenue"], "leads": r["leads"],
                    "stage_rank": r["stage_rank"], "sessions": r["sessions"], "active_days": r["active_days"],
                    "max_sessions_day": r["max_sessions_day"], "engaged_sessions": r["engaged_sessions"],
                    "bounce_sessions": r["bounce_sessions"], "bot_click_sessions": r["bot_click_sessions"],
                    "ua_botlike_sessions": r["ua_botlike_sessions"], "user_agents": r["user_agents"],
                    "tz_known_sessions": r["tz_known_sessions"], "tz_mismatch_sessions": r["tz_mismatch_sessions"],
                    "proxycheck_risk": r["proxycheck_risk"], "has_vendor_answer": r["has_vendor_answer"],
                    "experiment_ids": r["experiment_ids"]})
    write_csv("ip_bot_verdict.csv", out)

    verdicts = ["human", "likely_human", "unknown", "suspicious", "bot"]
    counts = {v: sum(1 for o in out if o["verdict"] == v) for v in verdicts}

    # Verdict by MoM label, to show how the two relate.
    by_label = []
    for lab, test_fn in (("real_person (revenue > 0)", lambda o: o["revenue"] > 0),
                         ("lead, no revenue", lambda o: o["leads"] > 0 and o["revenue"] <= 0),
                         ("no lead", lambda o: o["leads"] == 0)):
        grp = [o for o in out if test_fn(o)]
        row = {"mom_label": lab, "ips": len(grp)}
        for v in verdicts:
            row[v] = sum(1 for o in grp if o["verdict"] == v)
            row[v + "_pct"] = pct(row[v], len(grp))
        by_label.append(row)
    write_csv("verdict_by_mom_label.csv", by_label)

    # Which strong signals produced the bot verdicts.
    reasons = [{"signal": s, "bot_ips": sum(1 for o in out if o["verdict"] == "bot" and s in o["strong_signals"].split())}
               for s in strong]
    write_csv("bot_reasons.csv", reasons)

    # Per experiment
    exp = {}
    for o in out:
        for e in (o["experiment_ids"] or "").split():
            d = exp.setdefault(e, dict({"experiment_id": e, "ips": 0}, **{v: 0 for v in verdicts}))
            d["ips"] += 1
            d[o["verdict"]] += 1
    exp_rows = sorted(exp.values(), key=lambda d: -d["ips"])
    for d in exp_rows:
        d["bot_pct"] = pct(d["bot"], d["ips"])
        d["bot_or_suspicious_pct"] = pct(d["bot"] + d["suspicious"], d["ips"])
        d["human_or_likely_pct"] = pct(d["human"] + d["likely_human"], d["ips"])
    write_csv("verdict_per_experiment.csv", exp_rows)

    # The rule is only useful if it rarely calls a proven human a bot: measure it on paying IPs with
    # the human-proof override switched off.
    paying_bot = sum(1 for r in paying if any(signals(r, velocity)[s] for s in strong))
    checks = {
        "IPs equal a direct count": n == direct["ips"],
        "sessions equal a direct count": sum(r["sessions"] for r in rows) == direct["sessions"],
        "every IP has exactly one verdict": sum(counts.values()) == n,
        "no paying IP is called bot": all(o["verdict"] == "human" for o in out if o["revenue"] > 0),
        "every strong signal is within %.0f%% FPR on paying IPs" % MAX_FPR:
            all(t["FPR_pct"] <= MAX_FPR for t in test if t["strength"] == "strong"),
        "combined strong rules stay within 5%% of paying IPs": pct(paying_bot, len(paying)) <= 5,
    }
    summary = {"window": [START, END], "session_ips": n, "sessions": direct["sessions"], "paying_ips": len(paying),
               "max_fpr_pct": MAX_FPR, "velocity_threshold_sessions_per_day": velocity,
               "strong_signals": strong, "weak_signals": weak,
               "verdicts": counts, "verdict_pct": {v: pct(counts[v], n) for v in verdicts},
               "combined_rule_fpr_on_paying_pct": pct(paying_bot, len(paying)),
               "signal_test": test, "by_mom_label": by_label, "bot_reasons": reasons,
               "experiments": len(exp_rows), "checks": checks}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, default=str)
    print(json.dumps({k: summary[k] for k in ("session_ips", "velocity_threshold_sessions_per_day", "strong_signals",
                                               "weak_signals", "verdicts", "combined_rule_fpr_on_paying_pct", "checks")},
                     indent=1, default=str))
    for t in test:
        print(t)
    for b in by_label:
        print(b)


if __name__ == "__main__":
    main()
