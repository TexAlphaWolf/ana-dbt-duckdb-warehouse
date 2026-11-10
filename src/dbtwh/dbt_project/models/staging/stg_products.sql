select
    product_id,
    category,
    price_cents,
    cost_cents
from {{ source('raw', 'products') }}
