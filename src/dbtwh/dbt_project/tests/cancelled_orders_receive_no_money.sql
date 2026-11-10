-- A cancelled order has no captured payment (failed attempts are allowed: they are not money).
select o.order_id, p.paid_cents
from {{ ref('stg_orders') }} as o
inner join {{ ref('int_order_payments') }} as p on p.order_id = o.order_id
where o.status = 'cancelled'
