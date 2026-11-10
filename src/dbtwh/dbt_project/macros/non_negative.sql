{# Generic test: no row has a negative value in the column. #}
{% test non_negative(model, column_name) %}
    select * from {{ model }} where {{ column_name }} < 0
{% endtest %}
