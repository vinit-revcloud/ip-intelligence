-- ============================================================================
-- IP INTELLIGENCE - REVIEW QUERIES
--
-- Paste any block below into the Athena console. Pick workgroup "ipintel"
-- and database "unified". Every query here has been run; the numbers in the
-- comments are what it returned on 2026-09-11.
--
-- WHAT THIS DATA IS, IN ONE PARAGRAPH
-- We collected every internet address (IP address) that has ever appeared in
-- our website sessions or our ad-click stream. That is 4,956,391 addresses.
-- For each one we ask several outside companies two questions: where is this
-- address, and is it hiding something. Each company's answer is stored as its
-- own row. We never merge their answers into one verdict, because the whole
-- point is to see where they disagree.
--
-- THE FOUR TABLES
--   ip_geo                     what each company says the LOCATION is
--   ip_intelligence            what each company says about PROXY / BOT risk
--   ip_geo_analytics           the scoring working-out for location
--   ip_intelligence_analytics  the scoring working-out for risk
--
-- The rule to remember: one row = one company's opinion about one address.
-- Seven companies answer location questions, four answer risk questions, so
-- one address can have up to eleven rows across the two main tables.
-- ============================================================================


-- ============================================================================
-- SECTION A - WHAT IS HERE
-- ============================================================================

-- A1. How big is each table?
-- Read it as: rows = opinions, addresses = distinct IPs, sources = companies.
--
-- Returned:
--   ip_intelligence            9,404,725 rows   4,956,392 addresses   4 sources
--   ip_intelligence_analytics  9,404,725 rows   4,956,392 addresses   4 sources
--   ip_geo                     4,966,911 rows   4,956,391 addresses   7 sources
--   ip_geo_analytics              14,735 rows       2,105 addresses   7 sources
--
-- Why is ip_geo_analytics so much smaller? It only holds rows where we could
-- actually compare companies against each other. That needs at least two
-- companies to have answered, and only 2,105 addresses have that. For the
-- other 4.95 million, only IP2Location answered, and one opinion cannot
-- disagree with itself.
SELECT 'ip_geo'                    AS table_name, count(*) AS rows,
       count(DISTINCT ip_address)  AS addresses, count(DISTINCT vendor) AS sources
FROM unified.ip_geo
UNION ALL SELECT 'ip_geo_analytics', count(*), count(DISTINCT ip_address), count(DISTINCT vendor)
FROM unified.ip_geo_analytics
UNION ALL SELECT 'ip_intelligence', count(*), count(DISTINCT ip_address), count(DISTINCT vendor)
FROM unified.ip_intelligence
UNION ALL SELECT 'ip_intelligence_analytics', count(*), count(DISTINCT ip_address), count(DISTINCT vendor)
FROM unified.ip_intelligence_analytics
ORDER BY rows DESC;


-- A2. What columns does each table have?
-- Run this instead of guessing at column names.
SELECT table_name, ordinal_position AS position, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'unified'
  AND table_name IN ('ip_geo','ip_geo_analytics','ip_intelligence','ip_intelligence_analytics')
ORDER BY table_name, ordinal_position;


-- ============================================================================
-- SECTION B - WHO ANSWERED WHAT
-- ============================================================================

-- B1. Location: which company covers how many addresses, and how complete?
-- "Fill" means: of the rows this company has, what share carry a real value
-- rather than a blank.
--
-- Returned:
--   ip2location_db11   4,956,391 addresses   state 100%   city 100%   zip 99.8%
--   proxycheck_io          2,105 addresses   state 100%   city 100%   zip 86.8%
--   dbip_combined          2,105 addresses   state 100%   city 100%   zip  0.0%
--   maxmind_geolite2       2,105 addresses   state 99.3%  city 94.1%  zip 94.1%
--   geojs_io               2,105 addresses   state 99.3%  city 94.1%  zip  0.0%
--   ipwho_is               1,050 addresses   state 100%   city 100%   zip 100%
--   ipinfo_io              1,050 addresses   state 100%   city 100%   zip 100%
--
-- Only IP2Location reaches every address. It is a file we download, so looking
-- up five million addresses costs nothing. The others are paid web services
-- charged per call, so we only asked them about a sample.
SELECT vendor AS source,
       count(DISTINCT ip_address) AS addresses,
       round(100.0 * count_if(state    IS NOT NULL) / count(*), 1) AS state_fill_pct,
       round(100.0 * count_if(city     IS NOT NULL) / count(*), 1) AS city_fill_pct,
       round(100.0 * count_if(zip_code IS NOT NULL) / count(*), 1) AS zip_fill_pct
FROM unified.ip_geo
GROUP BY vendor
ORDER BY addresses DESC;


-- B2. Risk: which company covers how many, and what did they flag?
-- "Answered" matters here. A company can have a row for an address and still
-- have no opinion about it. Those are counted separately on purpose.
--
-- Returned:
--   source               rows       answered   flagged   had no opinion
--   ip2proxy_px12        4,956,391  16,806     16,806    4,939,585
--   fraudlogix_tune      4,446,228  4,446,228  404,291   0
--   authoritative_lists  2,105      2,105      540       0
--   proxycheck_io        1          1          1         0
--
-- IP2Proxy has a row for every address but an opinion about almost none. That
-- is the difference between "we asked and it said nothing" and "we never
-- asked", and it is why had_no_opinion is its own column.
--
-- FraudLogix is the surprise. It costs nothing extra because the answers were
-- already sitting in our own ad-click data. It covers 90% of all addresses and
-- is the only source that identifies bots at all.
SELECT vendor AS source,
       count(*)                    AS rows,
       count_if(has_answer)        AS answered,
       count_if(flagged)           AS flagged_as_risky,
       count_if(verdict_class = 'no_answer') AS had_no_opinion
FROM unified.ip_intelligence_analytics
GROUP BY vendor
ORDER BY rows DESC;


-- ============================================================================
-- SECTION C - IS THE DATA TRUSTWORTHY
-- These are the checks that have actually caught bugs in this project.
-- ============================================================================

-- C1. Are there duplicate rows?
-- There must be exactly one row per address per company. Any other number
-- means a join went wrong and every count built on it is inflated.
-- Returned: 0 and 0. Correct.
SELECT 'ip_geo' AS table_name, count_if(n > 1) AS duplicate_rows
FROM (SELECT ip_address, vendor, count(*) AS n FROM unified.ip_geo GROUP BY ip_address, vendor)
UNION ALL
SELECT 'ip_intelligence', count_if(n > 1)
FROM (SELECT ip_address, vendor, count(*) AS n FROM unified.ip_intelligence GROUP BY ip_address, vendor);


-- C2. The three-state rule, which is the easiest thing to get wrong here.
-- Every yes/no column has THREE possible states, not two:
--   true   the company says yes
--   false  the company says no
--   empty  the company never answered
--
-- Empty is NOT a no. If you count empties as "no", you turn silence into a
-- clean bill of health for millions of addresses. This query shows the split
-- so you can see how much of the table is silence.
--
-- Returned:
--   question       said yes   said no     never answered
--   is_proxy       335,679    4,129,461   4,939,585
--   is_bot          80,562    4,365,666   4,958,497
--   is_datacenter   18,486    4,446,654   4,939,585
--   is_vpn           3,654    4,461,486   4,939,585
--
-- Around 4.9 million rows are silence on every question. That is more than half
-- the table. Counting those as "no" would be the single most damaging mistake
-- you could make with this data.
SELECT 'is_proxy' AS question,
       count_if(is_proxy = true)  AS said_yes,
       count_if(is_proxy = false) AS said_no,
       count_if(is_proxy IS NULL) AS never_answered
FROM unified.ip_intelligence
UNION ALL SELECT 'is_bot', count_if(is_bot = true), count_if(is_bot = false), count_if(is_bot IS NULL)
FROM unified.ip_intelligence
UNION ALL SELECT 'is_datacenter', count_if(is_datacenter = true), count_if(is_datacenter = false), count_if(is_datacenter IS NULL)
FROM unified.ip_intelligence
UNION ALL SELECT 'is_vpn', count_if(is_vpn = true), count_if(is_vpn = false), count_if(is_vpn IS NULL)
FROM unified.ip_intelligence;


-- C3. Did every source survive the build?
-- A source that silently returns zero rows looks exactly like a source that
-- has nothing to say. This happened once already in this project: a broken
-- text pattern made FraudLogix return nothing and nobody noticed for a while.
-- Expect 7 location sources and 4 risk sources.
SELECT 'ip_geo' AS table_name, count(DISTINCT vendor) AS sources_present,
       array_join(array_agg(DISTINCT vendor ORDER BY vendor), ', ') AS names
FROM unified.ip_geo
UNION ALL
SELECT 'ip_intelligence', count(DISTINCT vendor),
       array_join(array_agg(DISTINCT vendor ORDER BY vendor), ', ')
FROM unified.ip_intelligence;


-- ============================================================================
-- SECTION D - LOOK AT ONE ADDRESS
-- This is the clearest way to understand the shape of the data.
-- ============================================================================

-- D1. What does every company say about the location of one address?
-- Swap the address for any other one you want to inspect.
-- Try 146.75.164.0 to see how bad the disagreement gets. Four companies say
-- Dallas, Texas. Two say Stillwater, Oklahoma. IP2Location says Mexico City.
-- Same address, same moment, three different countries' worth of answers.
-- This is the entire reason we store each company separately.
SELECT vendor AS source, state, city, zip_code, latitude, longitude, timezone
FROM unified.ip_geo
WHERE ip_address = '146.75.164.0'
ORDER BY vendor;


-- D2. The location table joined to its scoring twin.
-- ip_geo holds the raw answers. ip_geo_analytics holds the working-out:
-- what the majority said, how many backed it, and whether this company agreed.
--
-- "Consensus" = the most common answer among the other companies.
-- "row_agreement_pct" = how much of this company's answer matched that majority.
SELECT g.vendor AS source, g.state, g.city,
       a.consensus_state, a.state_votes AS companies_backing_consensus,
       a.state_matches_consensus AS this_source_agreed,
       a.row_agreement_pct       AS agreement_pct
FROM unified.ip_geo g
JOIN unified.ip_geo_analytics a
  ON a.ip_address = g.ip_address AND a.vendor = g.vendor
WHERE g.ip_address = '146.75.164.0'
ORDER BY g.vendor;


-- D3. What does every company say about the RISK of one address?
-- Remember the three-state rule: an empty cell means that company never
-- answered, not that the answer was no.
SELECT i.vendor AS source,
       i.is_proxy, i.is_vpn, i.is_datacenter, i.is_bot,
       i.isp, i.asn,
       a.has_answer, a.flagged, a.fraud_reason, a.verdict_class
FROM unified.ip_intelligence i
JOIN unified.ip_intelligence_analytics a
  ON a.ip_address = i.ip_address AND a.vendor = i.vendor
WHERE i.ip_address = '146.75.164.0'
ORDER BY i.vendor;


-- ============================================================================
-- SECTION E - WHAT THE DATA ACTUALLY SAYS
-- ============================================================================

-- E1. How much of our traffic comes from something suspicious?
-- Each line counts DISTINCT addresses where at least one company said yes.
--
-- Returned:
--   flagged by at least one source   418,610 addresses
--   called a proxy                   333,693
--   called a bot                      80,562
--   called a datacenter               18,345
--
-- Out of 4,956,391 addresses. So 8.4% were flagged by at least one source, and
-- 1.6% were called bots.
SELECT 'flagged by at least one source' AS finding, count(DISTINCT ip_address) AS addresses
FROM unified.ip_intelligence_analytics WHERE flagged
UNION ALL SELECT 'called a bot',        count(DISTINCT ip_address) FROM unified.ip_intelligence WHERE is_bot
UNION ALL SELECT 'called a proxy',      count(DISTINCT ip_address) FROM unified.ip_intelligence WHERE is_proxy
UNION ALL SELECT 'called a datacenter', count(DISTINCT ip_address) FROM unified.ip_intelligence WHERE is_datacenter
ORDER BY addresses DESC;


-- E2. Why were addresses flagged? The reason codes, most common first.
-- This tells you what kind of bad traffic we actually have, rather than just
-- how much.
--
-- Returned (top rows):
--   PROXY                  314,953 addresses
--   NON_HUMAN_SCRIPT        71,267
--   PUB/DCH                 14,899   (IP2Proxy: public proxy in a datacenter)
--   BOT_GENERATED            9,295
--   MOBILE_PROXY_SIGNALS     3,382
--   VPN                      3,116
--   DATA_CENTER              2,249
--   icloud_relay               538
--
-- Proxies dominate. The two genuinely automated categories, NON_HUMAN_SCRIPT
-- and BOT_GENERATED, together account for 80,562 addresses.
SELECT fraud_reason AS reason, count(DISTINCT ip_address) AS addresses
FROM unified.ip_intelligence_analytics
WHERE flagged AND fraud_reason IS NOT NULL
GROUP BY fraud_reason
ORDER BY addresses DESC
LIMIT 20;


-- E3. Where is our traffic from? Top 15 states.
-- Uses IP2Location because it is the only source covering every address.
--
-- Returned (top rows): Florida 429,391 (8.7%), California 425,068 (8.6%),
-- Texas 379,654 (7.7%), New York 286,295 (5.8%), Ohio 241,165 (4.9%).
SELECT state, count(*) AS addresses,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct_of_total
FROM unified.ip_geo
WHERE vendor = 'ip2location_db11' AND state IS NOT NULL
GROUP BY state
ORDER BY addresses DESC
LIMIT 15;


-- ============================================================================
-- SECTION F - THE SCORECARDS
-- These are the two tables the comparison dashboard reads.
-- ============================================================================

-- F1. Location scorecard.
--   fill_rate_pct   how often this company gave an answer at all
--   agreement_pct   when it answered, how often it matched the other companies
--   score           agreement multiplied by fill rate
--
-- The multiplication is the important part. A company that answers rarely but
-- accurately cannot win on accuracy alone, because an answer you do not get is
-- worth nothing.
--
-- IMPORTANT: geojs_io is marked excluded_from_voting. Its answers are identical
-- to maxmind_geolite2 on every single field, so counting both would let one
-- company's opinion vote twice.
--
-- NOTE ON THE WORD "AGREEMENT": this is agreement between companies, not
-- correctness. We have no verified ground truth for where an address really
-- is. Companies can agree with each other and all be wrong together.
SELECT vendor AS source, ips_tested, fill_rate_pct, agreement_pct,
       state_truth_pct, city_truth_pct, zip_truth_pct,
       score, excluded_from_voting
FROM unified.vendor_overview_geo
ORDER BY score DESC;


-- F2. Risk scorecard.
--   precision_infra_pct  when this company flagged something, how often was it
--                        on a published list of known proxy ranges
--   recall_infra_pct     of the addresses on those published lists, how many
--                        did this company catch
--
-- Returned:
--   authoritative_lists  2,105 tested  100% fill  score 100.0
--   fraudlogix_tune      2,105 tested   80% fill  score  46.9
--   ip2proxy_px12        2,105 tested    0.2% fill  score  0.0
--
-- authoritative_lists scores 100 because it IS the reference everything else is
-- measured against. It is a list of published ranges, not a detector. It cannot
-- find anything that is not already public. Do not read its 100 as "best".
--
-- All three are scored against the same fixed set of 2,105 addresses. Scoring
-- each company only on the addresses it happened to cover would make fill rate
-- read 100% for everyone and measure nothing.
SELECT vendor AS source, ips_tested, answered, fill_rate_pct,
       flagged, bot_flagged, precision_infra_pct, recall_infra_pct,
       bot_metric_status, score
FROM unified.vendor_overview_proxy
ORDER BY score DESC;


-- ============================================================================
-- SECTION G - PERFORMANCE
-- ============================================================================

-- G1. Fast lookup: filter on ip_address.
-- Both big tables are split into 64 files by address, so filtering on an exact
-- address reads one file instead of all of them. This scans about 1.5 MB.
-- ALWAYS filter on ip_address when you can.
SELECT * FROM unified.ip_geo WHERE ip_address = '76.36.92.184';

-- G2. Slow: no address filter.
-- This reads the whole table, about 100 MB for ip_geo and 200 MB for
-- ip_intelligence. Fine occasionally, expensive in a loop or a dashboard that
-- refreshes. Add a LIMIT and it does NOT help, because the sort runs first.
-- SELECT * FROM unified.ip_intelligence ORDER BY ip_address LIMIT 100;


-- ============================================================================
-- GLOSSARY
--
-- IP address        the number that identifies a device on the internet.
-- vendor / source   a company whose opinion we store. Seven for location,
--                   four for risk.
-- proxy             a relay that hides the real origin of the traffic.
-- VPN               virtual private network. A specific kind of proxy.
-- datacenter        traffic from a server farm rather than a home or phone.
--                   Usually automation, not a person.
-- bot               automated traffic pretending to be a person.
-- consensus         the most common answer among the companies. NOT the truth.
-- agreement         how often a company matches the consensus. NOT accuracy.
-- fill rate         how often a company gives any answer at all.
-- has_answer        whether this company actually responded about this address.
--                   Separates "asked, said nothing" from "never asked".
-- flagged           at least one risk signal came back true for this row.
-- verdict_class     a plain label for the outcome: confirmed, clean,
--                   unconfirmed flag, missed, or no answer.
-- truth_pct         how often a company matched the postal address on the
--                   customer record. Treat as weak: that address describes the
--                   property, not necessarily the person sitting at the device.
-- ============================================================================


-- ============================================================================
-- SECTION H - WHICH COLUMNS ARE ACTUALLY FILLED
--
-- H1-H4 rank every column of a table from most-filled to most-empty, so you can
-- see at a glance which columns carry data and which are nearly all blank.
--
-- H5-H8 are plain SELECTs with the columns listed in that same order, so the
-- useful data sits on the left of the result grid and the blanks trail off to
-- the right.
--
-- To adapt H1-H4 to any other table: list its columns once in the count() block
-- and once in the first ARRAY, and keep the c1..cN references lined up.
-- ============================================================================

-- H1. unified.ip_geo - columns ranked most-filled first.
WITH c AS (
  SELECT count(*) AS n,
    count(ip_address) c1,
    count(vendor) c2,
    count(state) c3,
    count(city) c4,
    count(zip_code) c5,
    count(latitude) c6,
    count(longitude) c7,
    count(timezone) c8,
    count(created_at) c9,
    count(updated_at) c10
  FROM unified.ip_geo
)
SELECT x.column_name,
       x.filled,
       c.n - x.filled                   AS empty,
       round(100.0 * x.filled / c.n, 2) AS filled_pct,
       CASE WHEN x.filled = 0         THEN 'always empty'
            WHEN x.filled = c.n       THEN 'always filled'
            WHEN x.filled < c.n / 100 THEN 'nearly empty'
            ELSE 'partly filled' END    AS status
FROM c CROSS JOIN UNNEST(
  ARRAY['ip_address','vendor','state','city','zip_code','latitude','longitude','timezone','created_at','updated_at'],
  ARRAY[c.c1,c.c2,c.c3,c.c4,c.c5,c.c6,c.c7,c.c8,c.c9,c.c10]
) AS x(column_name, filled)
ORDER BY x.filled DESC, x.column_name;

-- H2. unified.ip_geo_analytics - columns ranked most-filled first.
WITH c AS (
  SELECT count(*) AS n,
    count(ip_address) c1,
    count(vendor) c2,
    count(has_answer) c3,
    count(consensus_state) c4,
    count(consensus_city) c5,
    count(consensus_zip) c6,
    count(state_votes) c7,
    count(city_votes) c8,
    count(zip_votes) c9,
    count(state_matches_consensus) c10,
    count(city_matches_consensus) c11,
    count(zip_matches_consensus) c12,
    count(truth_state) c13,
    count(truth_city) c14,
    count(truth_zip) c15,
    count(state_matches_truth) c16,
    count(city_matches_truth) c17,
    count(zip_matches_truth) c18,
    count(row_agreement_pct) c19,
    count(row_truth_agreement_pct) c20
  FROM unified.ip_geo_analytics
)
SELECT x.column_name,
       x.filled,
       c.n - x.filled                   AS empty,
       round(100.0 * x.filled / c.n, 2) AS filled_pct,
       CASE WHEN x.filled = 0         THEN 'always empty'
            WHEN x.filled = c.n       THEN 'always filled'
            WHEN x.filled < c.n / 100 THEN 'nearly empty'
            ELSE 'partly filled' END    AS status
FROM c CROSS JOIN UNNEST(
  ARRAY['ip_address','vendor','has_answer','consensus_state','consensus_city','consensus_zip','state_votes','city_votes','zip_votes','state_matches_consensus','city_matches_consensus','zip_matches_consensus','truth_state','truth_city','truth_zip','state_matches_truth','city_matches_truth','zip_matches_truth','row_agreement_pct','row_truth_agreement_pct'],
  ARRAY[c.c1,c.c2,c.c3,c.c4,c.c5,c.c6,c.c7,c.c8,c.c9,c.c10,c.c11,c.c12,c.c13,c.c14,c.c15,c.c16,c.c17,c.c18,c.c19,c.c20]
) AS x(column_name, filled)
ORDER BY x.filled DESC, x.column_name;

-- H3. unified.ip_intelligence - columns ranked most-filled first.
WITH c AS (
  SELECT count(*) AS n,
    count(ip_address) c1,
    count(vendor) c2,
    count(is_proxy) c3,
    count(is_vpn) c4,
    count(is_tor) c5,
    count(is_datacenter) c6,
    count(is_bot) c7,
    count(is_compromised) c8,
    count(is_scraper) c9,
    count(is_anonymous) c10,
    count(isp) c11,
    count(asn) c12,
    count(created_at) c13,
    count(updated_at) c14
  FROM unified.ip_intelligence
)
SELECT x.column_name,
       x.filled,
       c.n - x.filled                   AS empty,
       round(100.0 * x.filled / c.n, 2) AS filled_pct,
       CASE WHEN x.filled = 0         THEN 'always empty'
            WHEN x.filled = c.n       THEN 'always filled'
            WHEN x.filled < c.n / 100 THEN 'nearly empty'
            ELSE 'partly filled' END    AS status
FROM c CROSS JOIN UNNEST(
  ARRAY['ip_address','vendor','is_proxy','is_vpn','is_tor','is_datacenter','is_bot','is_compromised','is_scraper','is_anonymous','isp','asn','created_at','updated_at'],
  ARRAY[c.c1,c.c2,c.c3,c.c4,c.c5,c.c6,c.c7,c.c8,c.c9,c.c10,c.c11,c.c12,c.c13,c.c14]
) AS x(column_name, filled)
ORDER BY x.filled DESC, x.column_name;

-- H4. unified.ip_intelligence_analytics - columns ranked most-filled first.
WITH c AS (
  SELECT count(*) AS n,
    count(ip_address) c1,
    count(vendor) c2,
    count(has_answer) c3,
    count(flagged) c4,
    count(fraud_reason) c5,
    count(is_masked_device) c6,
    count(risk_score) c7,
    count(known_infrastructure) c8,
    count(infrastructure_list) c9,
    count(verdict_class) c10
  FROM unified.ip_intelligence_analytics
)
SELECT x.column_name,
       x.filled,
       c.n - x.filled                   AS empty,
       round(100.0 * x.filled / c.n, 2) AS filled_pct,
       CASE WHEN x.filled = 0         THEN 'always empty'
            WHEN x.filled = c.n       THEN 'always filled'
            WHEN x.filled < c.n / 100 THEN 'nearly empty'
            ELSE 'partly filled' END    AS status
FROM c CROSS JOIN UNNEST(
  ARRAY['ip_address','vendor','has_answer','flagged','fraud_reason','is_masked_device','risk_score','known_infrastructure','infrastructure_list','verdict_class'],
  ARRAY[c.c1,c.c2,c.c3,c.c4,c.c5,c.c6,c.c7,c.c8,c.c9,c.c10]
) AS x(column_name, filled)
ORDER BY x.filled DESC, x.column_name;

-- H5. unified.ip_geo - filled columns on the left, emptiest on the right.
SELECT ip_address, vendor, created_at, updated_at, latitude, longitude, state, city, timezone, zip_code
FROM unified.ip_geo
LIMIT 100;

-- H6. unified.ip_geo_analytics - filled columns on the left, emptiest on the right.
SELECT ip_address, vendor, has_answer, consensus_state, consensus_city, consensus_zip, state_votes, city_votes, zip_votes, truth_state, truth_zip, truth_city, state_matches_truth, row_truth_agreement_pct, state_matches_consensus, row_agreement_pct, city_matches_consensus, city_matches_truth, zip_matches_truth, zip_matches_consensus
FROM unified.ip_geo_analytics
LIMIT 100;

-- H7. unified.ip_intelligence - filled columns on the left, emptiest on the right.
SELECT ip_address, vendor, created_at, updated_at, is_proxy, is_vpn, is_tor, is_datacenter, is_bot, isp, asn, is_compromised, is_scraper, is_anonymous
FROM unified.ip_intelligence
LIMIT 100;

-- H8. unified.ip_intelligence_analytics - filled columns on the left, emptiest on the right.
SELECT ip_address, vendor, has_answer, flagged, is_masked_device, known_infrastructure, verdict_class, fraud_reason, risk_score, infrastructure_list
FROM unified.ip_intelligence_analytics
LIMIT 100;
