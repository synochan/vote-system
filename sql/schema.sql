create extension if not exists pgcrypto;

create table if not exists public.raw_votes (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    poll_id text not null,
    choice text not null,
    edge_node_id text not null,
    created_at timestamptz not null,
    received_at timestamptz not null default now(),
    status text not null default 'pending' check (
        status in ('pending', 'processing', 'processed', 'duplicate', 'failed')
    ),
    retry_count integer not null default 0,
    error_message text,
    claimed_by text,
    claim_expires_at timestamptz,
    processed_at timestamptz
);

create index if not exists raw_votes_status_idx on public.raw_votes (status, received_at);
create index if not exists raw_votes_claim_expires_idx on public.raw_votes (claim_expires_at);

create table if not exists public.processed_votes (
    id uuid primary key default gen_random_uuid(),
    raw_vote_id uuid not null references public.raw_votes (id) on delete cascade,
    user_id text not null,
    poll_id text not null,
    choice text not null,
    edge_node_id text not null,
    created_at timestamptz not null,
    received_at timestamptz not null,
    processed_at timestamptz not null default now(),
    constraint processed_votes_unique_user_poll unique (user_id, poll_id)
);

create index if not exists processed_votes_processed_at_idx on public.processed_votes (processed_at);

create table if not exists public.processing_logs (
    id bigint generated always as identity primary key,
    raw_vote_id uuid references public.raw_votes (id) on delete set null,
    worker_id text not null,
    event text not null,
    details jsonb not null default '{}'::jsonb,
    logged_at timestamptz not null default now()
);

create or replace function public.claim_pending_votes(
    batch_size integer default 10,
    claimer text default 'worker-1',
    claim_ttl_seconds integer default 300
)
returns setof public.raw_votes
language plpgsql
security definer
set search_path = public
as $$
declare
    effective_batch integer := greatest(batch_size, 1);
begin
    return query
    with candidates as (
        select id
        from public.raw_votes
        where status = 'pending'
           or (status = 'processing' and claim_expires_at is not null and claim_expires_at < now())
        order by received_at
        limit effective_batch
        for update skip locked
    ),
    updated as (
        update public.raw_votes rv
        set status = 'processing',
            claimed_by = claimer,
            claim_expires_at = now() + make_interval(secs => claim_ttl_seconds)
        where rv.id in (select id from candidates)
        returning rv.*
    )
    select * from updated;
end;
$$;

create or replace function public.process_raw_vote(
    p_raw_vote_id uuid,
    p_worker_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_vote public.raw_votes%rowtype;
    v_processed_id uuid;
    v_result text;
begin
    select *
    into v_vote
    from public.raw_votes
    where id = p_raw_vote_id
    for update;

    if not found then
        return jsonb_build_object(
            'status', 'missing',
            'raw_vote_id', p_raw_vote_id
        );
    end if;

    if v_vote.status not in ('processing', 'pending') then
        return jsonb_build_object(
            'status', 'skipped',
            'raw_vote_id', v_vote.id,
            'current_status', v_vote.status
        );
    end if;

    insert into public.processed_votes (
        raw_vote_id,
        user_id,
        poll_id,
        choice,
        edge_node_id,
        created_at,
        received_at
    )
    values (
        v_vote.id,
        v_vote.user_id,
        v_vote.poll_id,
        v_vote.choice,
        v_vote.edge_node_id,
        v_vote.created_at,
        v_vote.received_at
    )
    on conflict (user_id, poll_id) do nothing
    returning id into v_processed_id;

    if v_processed_id is null then
        v_result := 'duplicate';
    else
        v_result := 'processed';
    end if;

    update public.raw_votes
    set status = v_result,
        processed_at = now(),
        claimed_by = p_worker_id,
        claim_expires_at = null,
        error_message = null
    where id = v_vote.id;

    insert into public.processing_logs (raw_vote_id, worker_id, event, details)
    values (
        v_vote.id,
        p_worker_id,
        v_result,
        jsonb_build_object(
            'user_id', v_vote.user_id,
            'poll_id', v_vote.poll_id,
            'choice', v_vote.choice,
            'edge_node_id', v_vote.edge_node_id
        )
    );

    return jsonb_build_object(
        'status', v_result,
        'raw_vote_id', v_vote.id,
        'processed_vote_id', v_processed_id
    );
exception
    when others then
        update public.raw_votes
        set status = 'failed',
            retry_count = retry_count + 1,
            error_message = sqlerrm,
            claim_expires_at = null,
            claimed_by = p_worker_id
        where id = p_raw_vote_id;

        insert into public.processing_logs (raw_vote_id, worker_id, event, details)
        values (
            p_raw_vote_id,
            p_worker_id,
            'failed',
            jsonb_build_object('error', sqlerrm)
        );

        return jsonb_build_object(
            'status', 'failed',
            'raw_vote_id', p_raw_vote_id,
            'error', sqlerrm
        );
end;
$$;

create or replace function public.reset_failed_or_stale_votes()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_count integer;
begin
    update public.raw_votes
    set status = 'pending',
        error_message = null,
        claimed_by = null,
        claim_expires_at = null
    where status = 'failed'
       or (status = 'processing' and claim_expires_at is not null and claim_expires_at < now());

    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

create or replace view public.vote_metrics as
select
    count(*) filter (where rv.status = 'pending') as pending_votes,
    count(*) filter (where rv.status = 'processing') as processing_votes,
    count(*) filter (where rv.status = 'processed') as processed_votes,
    count(*) filter (where rv.status = 'duplicate') as duplicate_votes,
    count(*) filter (where rv.status = 'failed') as failed_votes,
    avg(extract(epoch from (rv.received_at - rv.created_at))) filter (where rv.received_at is not null) as avg_ingestion_latency_seconds,
    avg(extract(epoch from (rv.processed_at - rv.created_at))) filter (where rv.processed_at is not null) as avg_end_to_end_latency_seconds
from public.raw_votes rv;
