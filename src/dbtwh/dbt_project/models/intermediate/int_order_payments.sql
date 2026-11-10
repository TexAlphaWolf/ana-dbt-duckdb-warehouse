-- One row per order that has money received: only captured payments count, failed attempts do not.
select
    order_id,
    count(*) as payment_count,
    sum(amount_cents) as paid_cents,
    min(paid_at) as first_paid_at,
    max(paid_at) as last_paid_at
from {{ ref('stg_payments') }}
where status = 'captured'
group by order_id
