{# The status as the source typed it (any case, stray spaces, US spelling) as one of the four real ones. #}
{% macro clean_status(column) -%}
    case lower(trim({{ column }}))
        when 'canceled' then 'cancelled'
        else lower(trim({{ column }}))
    end
{%- endmacro %}
