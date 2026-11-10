-- Revenue must be the same number whichever way it is added up: the monthly mart, the order fact, and the order lines
-- of orders that were not cancelled. Returns a row (a failure) if they differ.
with monthly as (select sum(net_revenue_cents) as total from {{ ref('mart_monthly_revenue') }}),
fact as (select sum(revenue_cents) as total from {{ ref('fct_orders') }}),
customers as (select sum(lifetime_revenue_cents) as total from {{ ref('dim_customers') }}),
products as (select sum(revenue_cents) as total from {{ ref('dim_products') }}),
lines as (
    select sum(i.net_cents) as total
    from {{ ref('stg_order_items') }} as i
    inner join {{ ref('stg_orders') }} as o on o.order_id = i.order_id
    where o.status <> 'cancelled'
)

select monthly.total as monthly, fact.total as fact, customers.total as customers, products.total as products, lines.total as lines
from monthly, fact, customers, products, lines
where monthly.total <> fact.total or fact.total <> customers.total or fact.total <> products.total or fact.total <> lines.total
