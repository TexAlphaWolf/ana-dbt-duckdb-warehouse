-- No order has received more money than it was worth.
select order_id, net_cents, paid_cents
from {{ ref('fct_orders') }}
where paid_cents > net_cents
