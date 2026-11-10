-- One row per customer, with what they have bought. Cancelled orders do not count.
with orders as (
    select
        customer_id,
        count(*) as order_count,
        sum(revenue_cents) as lifetime_revenue_cents,
        min(ordered_at) as first_order_at,
        max(ordered_at) as last_order_at
    from {{ ref('fct_orders') }}
    where is_revenue
    group by customer_id
)

select
    c.customer_id,
    c.email,
    c.country,
    c.channel,
    c.signup_date,
    coalesce(o.order_count, 0) as order_count,
    coalesce(o.lifetime_revenue_cents, 0) as lifetime_revenue_cents,
    o.first_order_at,
    o.last_order_at,
    date_trunc('month', o.first_order_at)::date as cohort_month
from {{ ref('stg_customers') }} as c
left join orders as o on o.customer_id = c.customer_id
