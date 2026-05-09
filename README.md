# Supabase Voting System Lab

This project rewrites the original Cloud Run / Pub/Sub / Firestore lab into a Supabase-based distributed voting system.

Architecture:
- `clients/edge_client.py` simulates independent edge nodes generating votes.
- `supabase/functions/vote/index.ts` acts as the ingestion API.
- `public.raw_votes` works as the queue table.
- `workers/process_votes.py` acts as the processing worker.
- `public.processed_votes` stores final deduplicated results.
- `public.processing_logs` stores worker events for debugging and analysis.

## Service Replacement Map

- `Cloud Run API` -> `Supabase Edge Function`
- `Cloud Run worker` -> `Python worker script` or another Edge Function
- `Pub/Sub` -> `raw_votes` queue table
- `Firestore` -> `Supabase Postgres`

## Project Structure

- `sql/schema.sql`: database schema, helper functions, metrics view
- `sql/analysis_queries.sql`: analysis queries for screenshots and report data
- `supabase/functions/vote/index.ts`: ingestion function
- `clients/edge_client.py`: edge vote generator and sender
- `workers/process_votes.py`: worker that claims and processes queued votes
- `.env.example`: required environment variables

## 1. Create the Supabase Project

1. Create a new project in Supabase.
2. Copy the project URL.
3. Copy the `anon` key.
4. Copy the `service_role` key from project settings.
5. Duplicate `.env.example` into `.env` and fill in the values.

Required environment variables:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_VOTE_ENDPOINT=https://your-project.supabase.co/functions/v1/vote
EDGE_NODE_ID=edge-node-1
WORKER_ID=worker-1
```

## 2. Create the Database

1. Open the Supabase `SQL Editor`.
2. Run `sql/schema.sql`.
3. Confirm that these objects exist:
   - `raw_votes`
   - `processed_votes`
   - `processing_logs`
   - `claim_pending_votes`
   - `process_raw_vote`
   - `reset_failed_or_stale_votes`
   - `vote_metrics`

Why this structure:
- `raw_votes` keeps every inbound vote, including duplicates and failures.
- `processed_votes` keeps the final deduplicated record.
- The unique constraint on `(user_id, poll_id)` provides idempotency.

## 3. Deploy the Edge Function

Create a Supabase Edge Function named `vote` and replace its contents with `supabase/functions/vote/index.ts`.

If you are using the Supabase CLI locally:

```powershell
supabase functions new vote
supabase functions deploy vote --project-ref your-project-ref
```

In the Supabase dashboard, set these function secrets:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Function behavior:
- accepts `POST` requests
- validates `user_id`, `poll_id`, `choice`, `edge_node_id`, `created_at`
- inserts records into `raw_votes`
- returns `202 Accepted`

## 4. Install Python Dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 5. Run the Edge Client

Example:

```powershell
python clients/edge_client.py --count 20 --duplicate-chance 0.25
```

What it does:
- generates votes with random choices
- sends them to the Supabase Edge Function
- retries on request failures
- optionally resends some successful votes to simulate duplication

Useful options:
- `--count`: number of votes
- `--poll-id`: poll identifier
- `--min-delay` and `--max-delay`: simulate network timing variability
- `--duplicate-chance`: simulate duplicate transmission
- `--max-retries`: retry attempts after failure

## 6. Run the Worker

Process queued votes once:

```powershell
python workers/process_votes.py --batch-size 10
```

Run continuously:

```powershell
python workers/process_votes.py --loop --batch-size 10 --poll-interval 3
```

Reset stale or failed votes before processing:

```powershell
python workers/process_votes.py --recover-stale --batch-size 10
```

Simulate a worker crash:

```powershell
python workers/process_votes.py --batch-size 10 --crash-after 5
```

What the worker does:
- claims pending votes from `raw_votes`
- inserts final records into `processed_votes`
- marks each raw vote as `processed`, `duplicate`, or `failed`
- logs events in `processing_logs`

## 7. Failure Scenarios for the Lab

### Duplicate transmission

Run:

```powershell
python clients/edge_client.py --count 20 --duplicate-chance 0.5
```

Expected result:
- `raw_votes` will contain more rows than `processed_votes`
- `processed_votes` will still only contain one row per `(user_id, poll_id)`

### Worker crash and recovery

1. Send votes with the client.
2. Start the worker with `--crash-after 5`.
3. Restart the worker with `--recover-stale`.

Expected result:
- some rows remain `processing` or `failed` after the crash
- the restarted worker moves them back to `pending`
- remaining votes are eventually processed

### Queue buildup

1. Send a larger burst of votes.
2. Delay starting the worker, or stop it temporarily.

Expected result:
- `raw_votes` accumulates pending rows
- once the worker starts again, the queue drains

## 8. Analysis Queries

Run `sql/analysis_queries.sql` in the SQL editor for screenshots and report metrics.

Recommended screenshots:
- `raw_votes` with mixed statuses
- `processed_votes` showing deduplicated final votes
- `processing_logs` showing `processed`, `duplicate`, and `failed`
- `vote_metrics` view output

## 9. Four-Person Task Division

### Person 1: Supabase setup and database
- Create the Supabase project
- Run `sql/schema.sql`
- Manage project URL, keys, and function secrets
- Verify tables and helper functions

### Person 2: Edge client
- Own `clients/edge_client.py`
- Tune retry logic and duplicate simulation
- Run edge-node experiments and collect logs

### Person 3: Ingestion API
- Own `supabase/functions/vote/index.ts`
- Deploy the `vote` Edge Function
- Validate successful inserts into `raw_votes`

### Person 4: Worker and analysis
- Own `workers/process_votes.py`
- Run failure and recovery tests
- Execute `sql/analysis_queries.sql`
- Prepare screenshots, findings, and reflection

## 10. Suggested Submission Notes

In your report, explain:
- how the system separates ingestion from processing
- how deduplication is enforced with `(user_id, poll_id)`
- how retries improve eventual delivery
- how the queue table replaces Pub/Sub behavior
- what trade-offs you observed between simplicity and reliability

## 11. Suggested Demo Flow

1. Show the deployed `vote` function.
2. Run the edge client and show votes entering `raw_votes`.
3. Run the worker and show votes moving into `processed_votes`.
4. Trigger duplicates and show deduplication working.
5. Simulate a worker crash and recovery.
6. Show metrics and reflection points.
