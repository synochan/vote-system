from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from dotenv import load_dotenv


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_vote(edge_node_id: str, poll_id: str) -> Dict[str, Any]:
    return {
        "user_id": str(uuid.uuid4()),
        "poll_id": poll_id,
        "choice": random.choice(["A", "B", "C"]),
        "edge_node_id": edge_node_id,
        "created_at": iso_now(),
    }


def send_vote(
    endpoint: str,
    anon_key: str,
    vote: Dict[str, Any],
    timeout: float,
    max_retries: int,
    duplicate_chance: float,
) -> None:
    headers = {
        "Content-Type": "application/json",
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
    }

    attempts = 0
    while attempts <= max_retries:
        attempts += 1
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(vote),
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            print(
                f"[EDGE] sent vote user_id={vote['user_id']} choice={vote['choice']} "
                f"attempt={attempts} vote_id={payload.get('vote_id')}"
            )
            break
        except requests.RequestException as exc:
            print(
                f"[EDGE] send failed user_id={vote['user_id']} "
                f"attempt={attempts} error={exc}"
            )
            if attempts > max_retries:
                print(f"[EDGE] giving up user_id={vote['user_id']}")
                return
            time.sleep(min(2**attempts, 5))

    if random.random() < duplicate_chance:
        try:
            duplicate_response = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(vote),
                timeout=timeout,
            )
            duplicate_response.raise_for_status()
            print(f"[EDGE] duplicate sent user_id={vote['user_id']}")
        except requests.RequestException as exc:
            print(f"[EDGE] duplicate failed user_id={vote['user_id']} error={exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate edge nodes sending votes to Supabase Edge Functions."
    )
    parser.add_argument("--count", type=int, default=20, help="Total votes to send.")
    parser.add_argument(
        "--poll-id",
        default="poll-1",
        help="Poll identifier used for generated votes.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=0.5,
        help="Minimum delay between sends in seconds.",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=1.5,
        help="Maximum delay between sends in seconds.",
    )
    parser.add_argument(
        "--duplicate-chance",
        type=float,
        default=0.2,
        help="Chance of intentionally resending a successful vote.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries after a failed send.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    endpoint = os.getenv("SUPABASE_VOTE_ENDPOINT")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    edge_node_id = os.getenv("EDGE_NODE_ID", "edge-node-1")

    if not endpoint or not anon_key:
        print("Missing SUPABASE_VOTE_ENDPOINT or SUPABASE_ANON_KEY in environment.")
        return 1

    for _ in range(args.count):
        vote = build_vote(edge_node_id=edge_node_id, poll_id=args.poll_id)
        send_vote(
            endpoint=endpoint,
            anon_key=anon_key,
            vote=vote,
            timeout=args.timeout,
            max_retries=args.max_retries,
            duplicate_chance=args.duplicate_chance,
        )
        time.sleep(random.uniform(args.min_delay, args.max_delay))

    return 0


if __name__ == "__main__":
    sys.exit(main())
