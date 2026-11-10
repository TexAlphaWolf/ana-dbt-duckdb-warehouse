-- One row per order: what was bought, at list value, with the discount, and what it cost the shop.
select
    i.order_id,
    count(*) as line_count,
    sum(i.quantity) as units,
    sum(i.gross_cents) as gross_cents,
    sum(i.discount_cents) as discount_cents,
    sum(i.net_cents) as net_cents,
    sum(i.quantity * p.cost_cents) as cost_cents
from {{ ref('stg_order_items') }} as i
inner join {{ ref('stg_products') }} as p on p.product_id = i.product_id
group by i.order_id
