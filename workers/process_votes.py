from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv


class SupabaseWorkerClient:
    def __init__(self, url: str, service_role_key: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    def rpc(self, function_name: str, payload: Dict[str, Any]) -> Any:
        response = requests.post(
            f"{self.url}/rest/v1/rpc/{function_name}",
            headers=self.headers,
            data=json.dumps(payload),
            timeout=20,
        )
        response.raise_for_status()
        if response.text:
            return response.json()
        return None

    def claim_pending_votes(
        self, batch_size: int, worker_id: str, claim_ttl_seconds: int
    ) -> List[Dict[str, Any]]:
        data = self.rpc(
            "claim_pending_votes",
            {
                "batch_size": batch_size,
                "claimer": worker_id,
                "claim_ttl_seconds": claim_ttl_seconds,
            },
        )
        return data or []

    def process_raw_vote(self, raw_vote_id: str, worker_id: str) -> Dict[str, Any]:
        return self.rpc(
            "process_raw_vote",
            {"p_raw_vote_id": raw_vote_id, "p_worker_id": worker_id},
        )

    def reset_failed_or_stale_votes(self) -> int:
        result = self.rpc("reset_failed_or_stale_votes", {})
        return int(result or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process queued votes from Supabase raw_votes."
    )
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--claim-ttl", type=int, default=300)
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds to wait before polling again in loop mode.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep polling for new votes instead of processing once.",
    )
    parser.add_argument(
        "--recover-stale",
        action="store_true",
        help="Reset stale or failed votes back to pending before processing.",
    )
    parser.add_argument(
        "--crash-after",
        type=int,
        default=0,
        help="Force the worker to stop after N votes for failure testing.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    worker_id = os.getenv("WORKER_ID", "worker-1")

    if not url or not service_role_key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")
        return 1

    client = SupabaseWorkerClient(url=url, service_role_key=service_role_key)

    if args.recover_stale:
        recovered = client.reset_failed_or_stale_votes()
        print(f"[WORKER] reset stale or failed votes: {recovered}")

    processed_total = 0

    while True:
        try:
            claimed_votes = client.claim_pending_votes(
                batch_size=args.batch_size,
                worker_id=worker_id,
                claim_ttl_seconds=args.claim_ttl,
            )
        except requests.RequestException as exc:
            print(f"[WORKER] failed to claim votes: {exc}")
            if not args.loop:
                return 1
            time.sleep(args.poll_interval)
            continue

        if not claimed_votes:
            print("[WORKER] no pending votes found")
            if not args.loop:
                break
            time.sleep(args.poll_interval)
            continue

        for vote in claimed_votes:
            raw_vote_id = vote["id"]
            try:
                result = client.process_raw_vote(raw_vote_id=raw_vote_id, worker_id=worker_id)
                print(f"[WORKER] raw_vote_id={raw_vote_id} result={result.get('status')}")
            except requests.RequestException as exc:
                print(f"[WORKER] processing failed raw_vote_id={raw_vote_id} error={exc}")

            processed_total += 1
            if args.crash_after and processed_total >= args.crash_after:
                print(f"[WORKER] simulated crash after {processed_total} processed votes")
                return 2

        if not args.loop:
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
