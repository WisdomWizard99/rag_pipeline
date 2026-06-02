-- stg_query_logs.sql
-- Staging model — cleans raw query logs
-- Adds 3 derived columns: latency_bucket, retrieval_quality, is_unanswered

with source as (

    select * from query_logs

),

cleaned as (

    select
        -- original columns, renamed cleanly
        id                                        as query_id,
        question,
        answer,
        round(latency_ms, 2)                      as latency_ms,
        top_k,
        num_sources,
        round(avg_score, 4)                       as avg_score,
        timestamp                                 as queried_at,

        -- is this query fast, normal or slow?
        case
            when latency_ms < 500  then 'fast'
            when latency_ms < 1000 then 'normal'
            else                        'slow'
        end                                       as latency_bucket,

        -- did retrieval find good matches?
        case
            when avg_score >= 0.6 then 'high'
            when avg_score >= 0.4 then 'medium'
            else                       'low'
        end                                       as retrieval_quality,

        -- did the LLM say it doesn't know?
        case
            when answer = 'I don''t know based on the provided context.'
            then true
            else false
        end                                       as is_unanswered

    from source
    where question is not null
      and length(trim(question)) > 0

)

select * from cleaned