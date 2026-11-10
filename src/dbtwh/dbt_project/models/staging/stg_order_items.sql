select
    order_id,
    line_no,
    product_id,
    quantity,
    unit_price_cents,
    discount_cents,
    quantity * unit_price_cents as gross_cents,
    quantity * unit_price_cents - discount_cents as net_cents
from {{ source('raw', 'order_items') }}
