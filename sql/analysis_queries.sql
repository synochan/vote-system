select * from public.vote_metrics;

select
    user_id,
    poll_id,
    choice,
    edge_node_id,
    created_at,
    received_at,
    processed_at,
    extract(epoch from (processed_at - created_at)) as end_to_end_latency_seconds
from public.processed_votes
order by processed_at desc
limit 25;

select
    status,
    count(*) as total_votes
from public.raw_votes
group by status
order by status;

select
    event,
    count(*) as total_events
from public.processing_logs
group by event
order by total_events desc;
