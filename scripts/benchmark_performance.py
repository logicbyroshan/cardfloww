"""
CardFlow Performance Benchmarking & Load Testing Suite
======================================================
Measures real-world endpoint latency percentiles (p50, p75, p90, p95, p99, max),
RPS, database queries, memory (RSS), and concurrency scaling under the 2 CPU / 2 GB RAM target envelope.

Usage: python scripts/benchmark_performance.py [--seed] [--concurrency 1,5,10,20,30,50] [--iterations 50]
"""
import os
import sys
import time
import json
import random
import statistics
import concurrent.futures
from typing import List, Dict, Any, Tuple

# Setup Django environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from tables.models import Table, IDCard
from organisation.models import Organisation
from core.views.idcard_card_api import (
    api_idcard_cards_json,
    api_idcard_filter_options,
    api_table_status_counts,
    api_idcard_update,
)
from core.services.idcard_table_service import IDCardTableService
from exports.excel import ExcelExporter

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

User = get_user_model()


def get_current_rss_mb() -> float:
    """Return process resident memory in MB."""
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    return 0.0


def ensure_benchmark_dataset(num_cards: int = 1500) -> Tuple[Any, Table, List[int]]:
    """Create or load a realistic benchmark dataset of N cards."""
    admin_user, _ = User.objects.get_or_create(
        username='benchmark_admin',
        defaults={'email': 'bench@cardflow.local', 'role': 'super_admin', 'is_staff': True, 'is_superuser': True}
    )

    prime_user, _ = User.objects.get_or_create(
        username='bench_prime_mgr',
        defaults={'email': 'bench_prime@cardflow.local', 'role': 'prime_manager'}
    )

    org = Organisation.objects.filter(name='Benchmark Public School').first()
    if not org:
        org = Organisation.objects.create(
            user=prime_user,
            name='Benchmark Public School',
            org_type='school',
        )

    fields = [
        {'name': 'Name', 'type': 'text', 'order': 1},
        {'name': 'Class', 'type': 'class', 'order': 2},
        {'name': 'Section', 'type': 'section', 'order': 3},
        {'name': 'Roll No', 'type': 'number', 'order': 4, 'is_unique': True},
        {'name': 'Father Name', 'type': 'text', 'order': 5},
        {'name': 'Mother Name', 'type': 'text', 'order': 6},
        {'name': 'Phone', 'type': 'text', 'order': 7},
        {'name': 'Address', 'type': 'textarea', 'order': 8},
        {'name': 'PHOTO', 'type': 'photo', 'order': 9},
        {'name': 'Blood Group', 'type': 'text', 'order': 10},
    ]

    table, _ = Table.objects.get_or_create(
        organisation=org,
        name='Class 1 to 12 All Students',
        defaults={'table_type': 'school_student', 'fields': fields, 'is_active': True}
    )

    current_count = IDCard.objects.filter(table=table).count()
    if current_count < num_cards:
        print(f"[*] Seeding benchmark dataset ({current_count} -> {num_cards} cards)...")
        first_names = ['Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Reyansh', 'Ayaan', 'Krishna', 'Ishaan', 'Ananya', 'Diya', 'Saanvi', 'Myra', 'Aadhya', 'Pari', 'Anika', 'Navya', 'Angel', 'Riya']
        last_names = ['Sharma', 'Verma', 'Gupta', 'Singh', 'Patel', 'Kumar', 'Mishra', 'Yadav', 'Jain', 'Mehta', 'Chouhan', 'Tiwari', 'Bhatt', 'Saxena', 'Pandey']
        classes = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th', '11th', '12th']
        sections = ['A', 'B', 'C', 'D']
        statuses = ['pending', 'verified', 'approved', 'download', 'pool']

        cards_to_create = []
        for i in range(current_count, num_cards):
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            cls_val = random.choice(classes)
            sec_val = random.choice(sections)
            status_val = statuses[i % len(statuses)]

            fd = {
                'Name': f"{fn} {ln}",
                'Class': cls_val,
                'Section': sec_val,
                'Roll No': str(1000 + i),
                'Father Name': f"Mr. {random.choice(first_names)} {ln}",
                'Mother Name': f"Mrs. {random.choice(first_names)} {ln}",
                'Phone': f"9826{random.randint(100000, 999999)}",
                'Address': f"House #{i + 1}, Sector {random.choice(['A','B','C'])}, Bhopal, MP",
                'PHOTO': f"adarshimg/O1_IMG{1000 + i}V1.jpg",
                'Blood Group': random.choice(['A+', 'B+', 'O+', 'AB+', 'O-']),
            }

            cards_to_create.append(IDCard(
                table=table,
                field_data=fd,
                status=status_val,
            ))

            if len(cards_to_create) >= 500:
                IDCard.objects.bulk_create(cards_to_create)
                cards_to_create = []

        if cards_to_create:
            IDCard.objects.bulk_create(cards_to_create)
        print(f"[+] Seeded {num_cards} cards successfully.")

    card_ids = list(IDCard.objects.filter(table=table).values_list('id', flat=True)[:100])
    return admin_user, table, card_ids


def run_single_benchmark(
    name: str,
    view_callable,
    iterations: int = 50,
    concurrency: int = 1
) -> Dict[str, Any]:
    """Execute iterations of a view request and collect timing percentiles."""
    latencies_ms: List[float] = []
    errors = 0

    def _exec_one():
        from django.db import connection
        t0 = time.perf_counter()
        try:
            resp = view_callable()
            dt = (time.perf_counter() - t0) * 1000.0
            status_code = getattr(resp, 'status_code', 200)
            if status_code >= 400:
                return dt, False
            return dt, True
        except Exception as e:
            dt = (time.perf_counter() - t0) * 1000.0
            return dt, False
        finally:
            if concurrency > 1:
                connection.close()

    start_rss = get_current_rss_mb()
    wall_start = time.perf_counter()

    if concurrency <= 1:
        for _ in range(iterations):
            dt, ok = _exec_one()
            latencies_ms.append(dt)
            if not ok:
                errors += 1
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_exec_one) for _ in range(iterations)]
            for fut in concurrent.futures.as_completed(futures):
                dt, ok = fut.result()
                latencies_ms.append(dt)
                if not ok:
                    errors += 1

    wall_duration = time.perf_counter() - wall_start
    end_rss = get_current_rss_mb()

    latencies_ms.sort()
    count = len(latencies_ms)
    p50 = statistics.median(latencies_ms) if count else 0
    p75 = latencies_ms[int(count * 0.75)] if count else 0
    p90 = latencies_ms[int(count * 0.90)] if count else 0
    p95 = latencies_ms[int(count * 0.95)] if count else 0
    p99 = latencies_ms[min(count - 1, int(count * 0.99))] if count else 0
    max_lat = max(latencies_ms) if count else 0
    rps = count / wall_duration if wall_duration > 0 else 0

    return {
        'name': name,
        'iterations': count,
        'concurrency': concurrency,
        'p50': p50,
        'p75': p75,
        'p90': p90,
        'p95': p95,
        'p99': p99,
        'max': max_lat,
        'rps': rps,
        'errors': errors,
        'wall_time_s': wall_duration,
        'rss_delta_mb': max(0.0, end_rss - start_rss),
        'end_rss_mb': end_rss,
    }


def main():
    print("=" * 80)
    print(" CardFlow Master Performance Benchmark & Profiling Suite")
    print(f" Target Resource Constraint: 2 CPU / 2 GB RAM / 3 Worker Threads")
    print(f" Initial Process RSS: {get_current_rss_mb():.2f} MB")
    print("=" * 80)

    factory = RequestFactory()
    user, table, sample_ids = ensure_benchmark_dataset(num_cards=1500)

    print(f"[+] Active Table: ID={table.id}, Name='{table.name}', Total Cards={table.id_cards.count()}")
    print("-" * 80)

    # 1. Warm-up
    print("[*] Running warm-up...")
    warmup_req = factory.get(f'/api/idcards/{table.id}/cards/json/?limit=100')
    warmup_req.user = user
    api_idcard_cards_json(warmup_req, table.id)
    print(f"[+] Warmup completed. Base RSS: {get_current_rss_mb():.2f} MB")
    print("-" * 80)

    benchmarks = [
        (
            "Cards JSON (Page 1, limit=100)",
            lambda: api_idcard_cards_json(
                _with_user(factory.get(f'/api/idcards/{table.id}/cards/json/?limit=100'), user),
                table.id
            )
        ),
        (
            "Cards JSON (Page 5, offset=400, limit=100)",
            lambda: api_idcard_cards_json(
                _with_user(factory.get(f'/api/idcards/{table.id}/cards/json/?offset=400&limit=100'), user),
                table.id
            )
        ),
        (
            "Cards JSON Filter (class=10th)",
            lambda: api_idcard_cards_json(
                _with_user(factory.get(f'/api/idcards/{table.id}/cards/json/?class=10th&limit=100'), user),
                table.id
            )
        ),
        (
            "Cards JSON Search (search=Sharma)",
            lambda: api_idcard_cards_json(
                _with_user(factory.get(f'/api/idcards/{table.id}/cards/json/?search=Sharma&limit=100'), user),
                table.id
            )
        ),
        (
            "Cards JSON Sort (sort=name-asc)",
            lambda: api_idcard_cards_json(
                _with_user(factory.get(f'/api/idcards/{table.id}/cards/json/?sort=name-asc&limit=100'), user),
                table.id
            )
        ),
        (
            "Filter Options API",
            lambda: api_idcard_filter_options(
                _with_user(factory.get(f'/api/idcards/{table.id}/filter-options/'), user),
                table.id
            )
        ),
        (
            "Status Counts Aggregation",
            lambda: api_table_status_counts(
                _with_user(factory.get(f'/api/idcards/{table.id}/status-counts/'), user),
                table.id
            )
        ),
        (
            "Duplicate Detection Scanner",
            lambda: IDCardTableService.find_duplicate_cards(table.id)
        ),
        (
            "Excel Exporter (100 Cards)",
            lambda: ExcelExporter().export_cards(table, list(IDCard.objects.filter(table=table)[:100]))
        ),
    ]

    results = []
    for name, callable_fn in benchmarks:
        print(f"[*] Benchmarking: {name} (50 iterations)...", flush=True)
        res = run_single_benchmark(name, callable_fn, iterations=50, concurrency=1)
        results.append(res)

    print("\n" + "=" * 95, flush=True)
    print(f"{'Endpoint / Workload':<42} | {'p50':>7} | {'p95':>7} | {'p99':>7} | {'Max':>7} | {'RPS':>7} | {'Err':>4}", flush=True)
    print("-" * 95, flush=True)
    for r in results:
        print(
            f"{r['name']:<42} | {r['p50']:>6.2f}ms | {r['p95']:>6.2f}ms | {r['p99']:>6.2f}ms | {r['max']:>6.2f}ms | {r['rps']:>7.1f} | {r['errors']:>4}",
            flush=True
        )
    print("=" * 95, flush=True)

    # Concurrency Scaling Test
    print("\n" + "=" * 80, flush=True)
    print(" Concurrency Scaling Test (Cards JSON View — Target: 3 Threads / 2 Cores)", flush=True)
    print("=" * 80, flush=True)

    concurrency_levels = [1, 3, 5, 10, 20, 30]
    concurrency_results = []

    for c in concurrency_levels:
        fn = lambda: api_idcard_cards_json(
            _with_user(factory.get(f'/api/idcards/{table.id}/cards/json/?limit=100'), user),
            table.id
        )
        res = run_single_benchmark(f"Concurrency={c}", fn, iterations=60, concurrency=c)
        concurrency_results.append(res)
        print(
            f"Concurrency {c:>2} users -> p50: {res['p50']:>6.2f}ms, p95: {res['p95']:>6.2f}ms, RPS: {res['rps']:>7.1f}, RSS: {res['end_rss_mb']:>6.1f} MB, Errors: {res['errors']}",
            flush=True
        )

    print("\n[+] Benchmark Suite Complete!", flush=True)


def _with_user(req, u):
    req.user = u
    return req


if __name__ == '__main__':
    main()
