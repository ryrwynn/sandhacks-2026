-- db/seed_caps.sql  AB 1482 caps for San Diego County (5% + San Diego CPI-U, April to April, max 10%)
INSERT INTO rent_caps (region, period_start, period_end, cap_pct, source_url) VALUES
  ('san_diego_county', '2025-08-01', '2026-07-31', 8.80, 'https://www.goodlifemgmt.com/blog/california-rent-cap-2026/'),
  ('san_diego_county', '2026-08-01', '2027-07-31', 8.20, 'https://www.goodlifemgmt.com/blog/california-rent-cap-2026/')
ON CONFLICT (region, period_start) DO UPDATE
  SET period_end = EXCLUDED.period_end, cap_pct = EXCLUDED.cap_pct, source_url = EXCLUDED.source_url;
