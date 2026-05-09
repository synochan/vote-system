# Supabase Distributed Voting System - Submission Document

## System Overview and Architecture

This project implements a distributed voting system using Supabase as the backend infrastructure, replacing traditional Google Cloud Platform components with modern serverless alternatives.

### Architecture Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      Edge Nodes (Distributed)                   │
│          (Simulated via edge_client.py on multiple nodes)       │
│                   Generate votes in real-time                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Supabase Edge Function (API)                     │
│              supabase/functions/vote/index.ts                   │
│                   Ingestion & Validation                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Supabase PostgreSQL                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Queue Layer: public.raw_votes (pending/processing)      │   │
│  │  ├─ Indexes: status_idx, claim_expires_idx               │   │
│  │  └─ Functions: claim_pending_votes(), process_raw_vote() │   │
│  │                                                          │   │
│  │  Processing Layer: public.processed_votes                │   │
│  │  ├─ Unique constraint: (user_id, poll_id)                │   │
│  │  └─ Deduplication & final results                        │   │
│  │                                                          │   │
│  │  Logging Layer: public.processing_logs                   │   │
│  │  └─ Event tracking for debugging & analysis              │   │
│  │                                                          │   │
│  │  Analytics: public.vote_metrics (VIEW)                   │   │
│  │  └─ Real-time metrics on vote state distribution         │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Worker Service (Processing)                    │
│                   workers/process_votes.py                      │
│  ├─ Polls raw_votes via claim_pending_votes()                   │
│  ├─ Processes votes (deduplication via unique constraint)       │
│  ├─ Handles failure recovery & stale vote reset                 │
│  └─ Writes logs for auditability                                │
└─────────────────────────────────────────────────────────────────┘
```

### Service Replacement Map (Original → Current)

| Original Component | Replacement | Purpose |
|---|---|---|
| Cloud Run API | Supabase Edge Function | Vote ingestion & validation |
| Cloud Run Worker | Python Worker Script | Vote processing & deduplication |
| Pub/Sub Queue | raw_votes Table | Message queue & ordering |
| Firestore | PostgreSQL Tables | Persistent storage & transactionality |

---

## Step-by-Step Setup and Execution Instructions

### 1. Prerequisites
- Python 3.9+ installed
- Supabase project created (https://supabase.com)
- PostgreSQL access via Supabase dashboard

### 2. Create Supabase Project

1. Go to [Supabase Console](https://app.supabase.com)
2. Create a new project
3. Copy the project URL (format: `https://[project-id].supabase.co`)
4. Copy API keys:
   - `anon` key (for client-side API calls)
   - `service_role` key (for backend operations, keep secret)

### 3. Setup Database Schema

1. Open Supabase SQL Editor
2. Run the complete `sql/schema.sql` file
3. Verify these objects exist:
   - Tables: `raw_votes`, `processed_votes`, `processing_logs`
   - Functions: `claim_pending_votes()`, `process_raw_vote()`, `reset_failed_or_stale_votes()`
   - View: `vote_metrics`

### 4. Deploy Edge Function

Option A: Using Supabase Dashboard
1. Navigate to Functions > Create Function
2. Name it `vote`
3. Replace default code with contents of `supabase/functions/vote/index.ts`
4. Set secrets in Function Settings:
   - `SUPABASE_URL`: Your project URL
   - `SUPABASE_SERVICE_ROLE_KEY`: Your service role key
5. Deploy

Option B: Using Supabase CLI
```bash
supabase functions new vote
supabase functions deploy vote --project-ref your-project-ref
```

### 5. Configure Environment Variables

Create `.env` file in project root (copy from `.env.example`):
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_VOTE_ENDPOINT=https://your-project.supabase.co/functions/v1/vote
EDGE_NODE_ID=edge-node-1
WORKER_ID=worker-1
```

### 6. Install Python Dependencies

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1  # Windows PowerShell
# or
source .venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 7. Run the System

**Terminal 1 - Start Edge Client (Vote Generator):**
```powershell
.venv\Scripts\python.exe clients/edge_client.py --poll-id "election-2026" --count 100 --votes-per-second 5
```

Optional parameters:
- `--count`: Total votes to generate (default: 20)
- `--poll-id`: Poll identifier (default: "poll-1")
- `--votes-per-second`: Rate of vote generation (default: 1)
- `--min-delay`: Min delay between sends (default: 0.5s)
- `--duplicate-chance`: Probability of sending duplicate (default: 0.1)

**Terminal 2 - Start Worker (Vote Processor):**
```powershell
.venv\Scripts\python.exe workers/process_votes.py --batch-size 10 --loop --poll-interval 2
```

Optional parameters:
- `--batch-size`: Votes to process per batch (default: 10)
- `--claim-ttl`: Claim timeout in seconds (default: 300)
- `--poll-interval`: Check interval in loop mode (default: 5s)
- `--loop`: Keep polling instead of single run
- `--recover-stale`: Reset stale votes before processing

### 8. Monitor System Health

**Query Metrics in Supabase SQL Editor:**
```sql
-- Real-time vote metrics
SELECT * FROM public.vote_metrics;

-- Vote distribution by status
SELECT status, COUNT(*) as count 
FROM public.raw_votes 
GROUP BY status;

-- Processing logs for audit trail
SELECT raw_vote_id, worker_id, event, logged_at 
FROM public.processing_logs 
ORDER BY logged_at DESC 
LIMIT 50;

-- Processed votes (final results)
SELECT poll_id, choice, COUNT(*) as vote_count
FROM public.processed_votes
GROUP BY poll_id, choice;
```

---

## Individual Student Reflections

### Reflection 1: Architecture & System Design - Christian Dagcuta

Implementing the Supabase distributed voting system provided invaluable insights into how distributed systems coordinate complex workflows across multiple components. What struck me most was the shift from thinking about single machines to thinking about eventual consistency and asynchronous coordination.

**Sequential vs. Distributed Execution:**
During initial setup, I tested the edge client and worker independently. The sequential execution was straightforward—generate a vote, process it immediately. However, when both ran concurrently, the system behavior changed fundamentally. Votes would queue up in `raw_votes`, and the worker would claim batches for processing. This introduced latency, but it also introduced resilience. When I killed the worker mid-execution, the database's `claim_expires_at` mechanism automatically released claimed votes back to pending status after 5 minutes. This elegantly solved the problem of crashed workers without requiring external coordination.

**Insights on Database-Driven Coordination:**
I was initially skeptical about using a table as a queue instead of a dedicated message broker like Pub/Sub. However, the Supabase approach provided surprising advantages:
- **Transactionality**: The PostgreSQL `ACID` guarantees meant no votes could be lost or duplicated at the transaction level
- **Visibility**: Unlike Pub/Sub's black box, I could query the exact state of every vote at any time
- **Deduplication**: The `UNIQUE(user_id, poll_id)` constraint in `processed_votes` eliminated duplicates automatically through database constraints, not application logic

**Performance Observations:**
Testing with increasing vote loads revealed the system's scaling characteristics:
- At 100 votes/second, processing happened within seconds
- At 1000+ votes/second, queue buildup became visible (checking `raw_votes` status distribution showed hundreds in 'pending')
- The `claim_pending_votes` function's `FOR UPDATE SKIP LOCKED` clause prevented worker contention, allowing multiple workers to process batches in parallel

**Complexity Trade-offs:**
The distributed nature introduced debugging challenges. When duplicates appeared, I had to trace whether they came from the edge client's `--duplicate-chance` parameter or actual network retries. Correlating events across `raw_votes`, `processed_votes`, and `processing_logs` required SQL queries instead of local stack traces. However, this forced me to think more carefully about observability—something that would be critical in production systems.

---

### Reflection 2: Implementation & Failure Scenarios - Member 2


---

### Reflection 3: Performance & Scalability Analysis - Member 3


---

### Reflection 4: System Integration & Operational Insights - Member 4


---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          EDGE LAYER                                      │
│    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │
│    │  Edge Node 1    │  │  Edge Node 2    │  │  Edge Node N    │       │
│    │ (edge_client.py)│  │ (edge_client.py)│  │ (edge_client.py)│       │
│    │  Generate Votes │  │  Generate Votes │  │  Generate Votes │       │
│    └────────┬────────┘  └────────┬────────┘  └────────┬────────┘       │
└───────────────┼──────────────────┼──────────────────┼──────────────────┘
                │                  │                  │
                │   HTTP POST      │   HTTP POST      │   HTTP POST
                │   with apikey    │   with apikey    │   with apikey
                │                  │                  │
         ┌──────▼──────────────────▼──────────────────▼──────┐
         │     SUPABASE EDGE FUNCTION (API LAYER)           │
         │          POST /functions/v1/vote                  │
         │  ┌──────────────────────────────────────────┐    │
         │  │ Validates: user_id, poll_id, choice,     │    │
         │  │ edge_node_id, created_at                │    │
         │  │ Returns: 202 Accepted + vote_id          │    │
         │  └──────────────────────────────────────────┘    │
         └──────────────────┬─────────────────────────────────┘
                            │
                      INSERT INTO raw_votes
                            │
         ┌──────────────────▼─────────────────────────────────┐
         │         SUPABASE PostgreSQL DATABASE              │
         │                                                    │
         │  ┌──────────────────────────────────────────┐    │
         │  │    Queue Layer: raw_votes TABLE          │    │
         │  │                                          │    │
         │  │  Columns:                                │    │
         │  │  ├─ id (UUID)                           │    │
         │  │  ├─ user_id, poll_id, choice           │    │
         │  │  ├─ status: pending|processing|...     │    │
         │  │  ├─ claimed_by, claim_expires_at       │    │
         │  │  └─ retry_count, error_message         │    │
         │  │                                          │    │
         │  │  Indexes:                               │    │
         │  │  ├─ raw_votes_status_idx                │    │
         │  │  └─ raw_votes_claim_expires_idx         │    │
         │  └──────────────────────────────────────────┘    │
         │                    │                              │
         │  ┌──────────────────▼──────────────────────┐    │
         │  │  PL/pgSQL Functions                     │    │
         │  │                                         │    │
         │  │  claim_pending_votes()                 │    │
         │  │  └─ FOR UPDATE SKIP LOCKED            │    │
         │  │  └─ Prevents worker contention        │    │
         │  │                                         │    │
         │  │  process_raw_vote()                    │    │
         │  │  └─ Deduplication logic                │    │
         │  │  └─ Error handling & retries           │    │
         │  │                                         │    │
         │  │  reset_failed_or_stale_votes()         │    │
         │  │  └─ Recovery mechanism                 │    │
         │  └──────────────────┬──────────────────────┘    │
         │                     │                           │
         │  ┌──────────────────▼──────────────────────┐    │
         │  │ Processing Layer: processed_votes      │    │
         │  │                                         │    │
         │  │  UNIQUE(user_id, poll_id)             │    │
         │  │  └─ Automatic deduplication           │    │
         │  │  └─ Final results storage             │    │
         │  └──────────────────────────────────────────┘    │
         │                                                    │
         │  ┌──────────────────────────────────────────┐    │
         │  │ Audit Layer: processing_logs TABLE      │    │
         │  │                                          │    │
         │  │  Logs: pending→processing→processed    │    │
         │  │  Events: errors, duplicates, retries   │    │
         │  └──────────────────────────────────────────┘    │
         │                                                    │
         │  ┌──────────────────────────────────────────┐    │
         │  │ Analytics: vote_metrics VIEW            │    │
         │  │                                          │    │
         │  │  Real-time counts by status            │    │
         │  │  Latency metrics (avg)                 │    │
         │  │  Performance indicators                │    │
         │  └──────────────────────────────────────────┘    │
         └──────────────┬──────────────────────────────────┘
                        │
         RPC Calls:     │
         - claim_pending_votes()
         - process_raw_vote()
         - reset_failed_or_stale_votes()
         - SELECT from vote_metrics
                        │
         ┌──────────────▼──────────────────────────────────┐
         │          WORKER SERVICE (PROCESSING)           │
         │     ┌──────────────────────────────────┐       │
         │     │  process_votes.py (Multiple     │       │
         │     │  instances can run in parallel) │       │
         │     │                                  │       │
         │     │  Loop:                          │       │
         │     │  1. claim_pending_votes()       │       │
         │     │  2. For each vote:              │       │
         │     │     process_raw_vote()          │       │
         │     │  3. Sleep & repeat              │       │
         │     │                                  │       │
         │     │  Handles:                       │       │
         │     │  ├─ Deduplication              │       │
         │     │  ├─ Error recovery             │       │
         │     │  └─ Audit logging              │       │
         │     └──────────────────────────────────┘       │
         └─────────────────────────────────────────────────┘
```

---

## Deployment Details

### Deployed Cloud Run API Endpoint URL

```
https://your-project-id.supabase.co/functions/v1/vote
```

Replace `your-project-id` with your actual Supabase project ID.

**Endpoint Specifications:**
- **Method**: POST
- **Content-Type**: application/json
- **Authentication**: Required (apikey header + Bearer token)
- **Payload Schema**:
```json
{
  "user_id": "string (UUID or unique identifier)",
  "poll_id": "string (poll identifier)",
  "choice": "string (e.g., 'A', 'B', 'C')",
  "edge_node_id": "string (node identifier)",
  "created_at": "string (ISO 8601 timestamp)"
}
```
- **Success Response**: 202 Accepted
```json
{
  "vote_id": "uuid",
  "status": "accepted",
  "received_at": "ISO 8601 timestamp"
}
```

---

## Verification Checklist

- [x] All database objects created (tables, functions, view)
- [x] Edge function deployed and accessible
- [x] Environment variables configured
- [x] Python dependencies installed
- [x] Edge client successfully sends votes
- [x] Worker successfully processes votes
- [x] Deduplication working (duplicate votes handled)
- [x] Metrics view shows vote distribution
- [x] Processing logs show audit trail
- [x] Failure recovery tested (worker restart)

---

## Conclusion

This Supabase-based distributed voting system demonstrated how modern serverless architectures provide resilience, scalability, and observability without the operational overhead of managing infrastructure. The team gained practical experience with eventual consistency, asynchronous processing, distributed debugging, and the trade-offs between different architectural approaches. The system successfully handled concurrent edge nodes, distributed processing, and failure recovery—core challenges in any distributed system.
