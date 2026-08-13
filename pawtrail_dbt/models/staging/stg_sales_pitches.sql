select
    pitch_id,
    state,
    cast(pitch_date as date) as pitch_date,
    cast(won as boolean) as won
from {{ ref('raw_sales_pitches') }}
