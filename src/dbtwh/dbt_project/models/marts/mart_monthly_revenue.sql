select
    order_month,
    count(*) as orders,
    sum(units) as units,
    sum(revenue_cents) as net_revenue_cents,
    sum(margin_cents) as gross_margin_cents,
    sum(revenue_cents)::double / count(*) as avg_order_value_cents
from {{ ref('fct_orders') }}
where is_revenue
group by order_month
order by order_month
