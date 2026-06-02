-- retrieval_quality.sql
-- Breakdown of queries by retrieval quality bucket
-- Answers: how often does retrieval succeed?

with base as (

    select * from {{ ref('stg_query_logs') }}

)

select
    retrieval_quality,
    count(*)                                as query_count,
    round(avg(latency_ms), 2)               as avg_latency_ms,
    round(avg(avg_score), 4)                as avg_score,
    sum(case when is_unanswered
        then 1 else 0 end)                  as unanswered_count,
    round(
        sum(case when is_unanswered
            then 1 else 0 end)
        * 100.0 / count(*), 2
    )                                       as unanswered_pct

from base
group by retrieval_quality
order by avg_score desc