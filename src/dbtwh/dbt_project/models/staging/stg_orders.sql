with ranked as (
    select
        order_id,
        customer_id,
        ordered_at::timestamp as ordered_at,
        {{ clean_status('status') }} as status,
        row_number() over (partition by order_id order by ordered_at) as copy_rank
    from {{ source('raw', 'orders') }}
)

select order_id, customer_id, ordered_at, status
from ranked
where copy_rank = 1
