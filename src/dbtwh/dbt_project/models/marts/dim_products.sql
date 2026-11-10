select
    p.product_id,
    p.category,
    p.price_cents,
    p.cost_cents,
    coalesce(s.units_sold, 0) as units_sold,
    coalesce(s.revenue_cents, 0) as revenue_cents
from {{ ref('stg_products') }} as p
left join (
    select
        i.product_id,
        sum(i.quantity) as units_sold,
        sum(i.net_cents) as revenue_cents
    from {{ ref('stg_order_items') }} as i
    inner join {{ ref('fct_orders') }} as o on o.order_id = i.order_id
    where o.is_revenue
    group by i.product_id
) as s on s.product_id = p.product_id
