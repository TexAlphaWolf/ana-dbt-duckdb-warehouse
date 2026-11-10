-- No customer orders before signing up.
select o.order_id, o.ordered_at, c.signup_date
from {{ ref('stg_orders') }} as o
inner join {{ ref('stg_customers') }} as c on c.customer_id = o.customer_id
where o.ordered_at::date < c.signup_date
