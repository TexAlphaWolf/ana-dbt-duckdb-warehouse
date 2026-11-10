with ranked as (
    select
        payment_id,
        order_id,
        paid_at::timestamp as paid_at,
        method,
        lower(trim(status)) as status,
        amount_cents,
        row_number() over (partition by payment_id order by paid_at) as copy_rank
    from {{ source('raw', 'payments') }}
)

select payment_id, order_id, paid_at, method, status, amount_cents
from ranked
where copy_rank = 1
