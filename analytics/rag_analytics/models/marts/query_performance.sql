-- query_performance.sql
-- Daily query performance summary
-- Answers: how is my RAG pipeline performing over time?

with base as (

    select * from {{ ref('stg_query_logs') }}

)

select
    date_trunc('day', queried_at)           as query_date,
    count(*)                                as total_queries,
    round(avg(latency_ms), 2)               as avg_latency_ms,
    round(min(latency_ms), 2)               as min_latency_ms,
    round(max(latency_ms), 2)               as max_latency_ms,
    round(avg(avg_score), 4)                as avg_retrieval_score,
    sum(case when is_unanswered
        then 1 else 0 end)                  as unanswered_count,
    round(
        sum(case when is_unanswered
            then 1 else 0 end)
        * 100.0 / count(*), 2
    )                                       as unanswered_pct

from base
group by date_trunc('day', queried_at)
order by query_date desc
