-- Of the customers whose first order was in a month (the cohort), how many ordered again k months later.
with activity as (
    select distinct customer_id, order_month
    from {{ ref('fct_orders') }}
    where is_revenue
),

cohorts as (
    select cohort_month, count(*) as cohort_size
    from {{ ref('dim_customers') }}
    where cohort_month is not null
    group by cohort_month
),

months as (
    select
        c.cohort_month,
        date_diff('month', c.cohort_month, a.order_month) as months_since,
        count(*) as active_customers
    from {{ ref('dim_customers') }} as c
    inner join activity as a on a.customer_id = c.customer_id
    where c.cohort_month is not null
    group by c.cohort_month, date_diff('month', c.cohort_month, a.order_month)
)

select
    m.cohort_month,
    m.months_since,
    k.cohort_size,
    m.active_customers,
    m.active_customers::double / k.cohort_size as retention_rate
from months as m
inner join cohorts as k on k.cohort_month = m.cohort_month
order by m.cohort_month, m.months_since
