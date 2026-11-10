{{ config(contract={'enforced': true}) }}

-- One row per order. An order counts as revenue unless it was cancelled.
select
    o.order_id::bigint as order_id,
    o.customer_id::bigint as customer_id,
    o.ordered_at::timestamp as ordered_at,
    date_trunc('month', o.ordered_at)::date as order_month,
    o.status::varchar as status,
    (o.status <> 'cancelled')::boolean as is_revenue,
    coalesce(t.units, 0)::bigint as units,
    coalesce(t.gross_cents, 0)::bigint as gross_cents,
    coalesce(t.discount_cents, 0)::bigint as discount_cents,
    coalesce(t.net_cents, 0)::bigint as net_cents,
    (case when o.status <> 'cancelled' then coalesce(t.net_cents, 0) else 0 end)::bigint as revenue_cents,
    (case when o.status <> 'cancelled' then coalesce(t.net_cents, 0) - coalesce(t.cost_cents, 0) else 0 end)::bigint
        as margin_cents,
    coalesce(p.paid_cents, 0)::bigint as paid_cents,
    (case
        when o.status = 'cancelled' then 'not_due'
        when coalesce(p.paid_cents, 0) = 0 then 'unpaid'
        when p.paid_cents < coalesce(t.net_cents, 0) then 'partial'
        else 'paid'
    end)::varchar as payment_state
from {{ ref('stg_orders') }} as o
left join {{ ref('int_order_totals') }} as t on t.order_id = o.order_id
left join {{ ref('int_order_payments') }} as p on p.order_id = o.order_id
