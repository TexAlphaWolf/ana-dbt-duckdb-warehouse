with ranked as (
    select
        customer_id,
        email,
        country,
        channel,
        signup_date::date as signup_date,
        updated_at::timestamp as updated_at,
        row_number() over (partition by customer_id order by updated_at desc) as version_rank
    from {{ source('raw', 'customers') }}
)

select customer_id, email, country, channel, signup_date, updated_at
from ranked
where version_rank = 1
