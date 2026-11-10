-- In the month of its first order every customer of a cohort is active: retention is 100% at month 0, and never above 100%.
select cohort_month, months_since, retention_rate
from {{ ref('mart_cohort_retention') }}
where (months_since = 0 and retention_rate <> 1) or retention_rate > 1 or months_since < 0
