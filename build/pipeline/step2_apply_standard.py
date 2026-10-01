"""One-off (19 Sep 2026): bring every existing ip_intelligence row in line with the step 2 standard
(is_bot = bad signal), the same rules vendors.py now applies to new answers. Writes ipintel_curated only;
unified follows at the next publish. Rollback: the snapshot id printed first."""
import os, sys
os.environ["AWS_PROFILE"] = "ipintel-builder"; os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
import apply, common as c, vendors as v
DB = c.DB
print("rollback snapshots: intel", apply.latest_snapshot("ip_intelligence"), "analytics", apply.latest_snapshot("ip_intelligence_analytics"))
types = ", ".join(c.lit(t) for t in sorted(v.BOT_TYPES))
clouds = ", ".join(c.lit(a) for a in sorted(v.CLOUD_ASNS))
rule = {
  "fraudlogix_tune": f"a.has_answer AND coalesce(a.fraud_reason, '') <> '{apply.FILLED_MARK}'",
  "ip2proxy_px12": "a.has_answer",
  "proxycheck_io": "a.has_answer",
}
value = {
  "fraudlogix_tune": "coalesce(a.fraud_reason, 'ACCEPTED') <> 'ACCEPTED'",
  "ip2proxy_px12": "true",
  "proxycheck_io": (f"(coalesce(i.is_proxy, false) OR coalesce(i.is_vpn, false) OR coalesce(i.is_tor, false) "
                    f"OR coalesce(i.is_datacenter, false) OR coalesce(i.is_compromised, false) OR coalesce(i.is_scraper, false) OR lower(trim(coalesce(a.fraud_reason, ''))) IN ({types}) "
                    f"OR upper(coalesce(i.asn, '')) IN ({clouds}) OR coalesce(a.risk_score, 0) >= {v.HIGH_RISK})"),
}
for vendor in rule:
    src = f"""SELECT i.ip_address, {value[vendor]} AS is_bot FROM {DB}.ip_intelligence i
              JOIN {DB}.ip_intelligence_analytics a ON a.ip_address = i.ip_address AND a.vendor = i.vendor
              WHERE i.vendor = '{vendor}' AND {rule[vendor]}"""
    n = c.scalar(f"SELECT count(*) FROM {DB}.ip_intelligence t JOIN ({src}) s ON s.ip_address = t.ip_address "
                 f"WHERE t.vendor = '{vendor}' AND t.is_bot IS DISTINCT FROM s.is_bot")
    if n:
        c.run(f"""MERGE INTO {DB}.ip_intelligence t USING ({src}) s
ON t.ip_address = s.ip_address AND t.vendor = '{vendor}'
WHEN MATCHED AND t.is_bot IS DISTINCT FROM s.is_bot THEN UPDATE SET is_bot = s.is_bot""", timeout_s=840)
    print(vendor, "is_bot changed on", n, "rows")
# analytics: flagged and verdict_class depend on is_bot
flag = ("(coalesce(i.is_proxy, false) OR coalesce(i.is_vpn, false) OR coalesce(i.is_tor, false) OR coalesce(i.is_datacenter, false) "
        "OR coalesce(i.is_bot, false) OR coalesce(i.is_compromised, false) OR coalesce(i.is_scraper, false))")
src = f"""SELECT a.ip_address, a.vendor, {flag} AS flagged,
  CASE WHEN NOT a.has_answer THEN 'no_answer' WHEN {flag} AND a.known_infrastructure THEN 'confirmed_by_published_range'
       WHEN {flag} THEN 'unconfirmed_flag' WHEN a.known_infrastructure THEN 'missed_known_infrastructure'
       ELSE 'agreed_not_flagged' END AS verdict_class
  FROM {DB}.ip_intelligence_analytics a JOIN {DB}.ip_intelligence i ON i.ip_address = a.ip_address AND i.vendor = a.vendor
  WHERE coalesce(a.fraud_reason, '') <> '{apply.FILLED_MARK}'"""
c.run(f"""MERGE INTO {DB}.ip_intelligence_analytics t USING ({src}) s
ON t.ip_address = s.ip_address AND t.vendor = s.vendor
WHEN MATCHED AND (t.flagged IS DISTINCT FROM s.flagged OR t.verdict_class IS DISTINCT FROM s.verdict_class)
THEN UPDATE SET flagged = s.flagged, verdict_class = s.verdict_class""", timeout_s=840)
print("analytics flagged / verdict_class refreshed")
print("FraudLogix rows filled from proxycheck.io (now incl. is_bot):", apply.fill_fraudlogix_from_proxycheck())
print("flag columns changed on", apply.refresh_flag_columns(), "rows")
print(apply.flag_column_checks())
