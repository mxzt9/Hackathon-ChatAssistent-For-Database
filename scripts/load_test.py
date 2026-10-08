"""Нагрузочный тест работающего сервера: python scripts/load_test.py --url http://127.0.0.1:8000."""

import argparse
import asyncio
import json
import time
from collections import Counter

import httpx


async def batch(client, label, concurrency, count, model=False):
    semaphore = asyncio.Semaphore(concurrency)
    durations, statuses, errors = [], Counter(), Counter()
    questions = [
        "Сколько всего студентов?",
        "Сколько всего преподавателей?",
        "Какова средняя оценка всех студентов?",
        "Сколько всего заявлений?",
    ]

    async def request(index):
        async with semaphore:
            started = time.perf_counter()
            try:
                if model:
                    response = await client.post(
                        "/api/query",
                        json={"question": questions[index % len(questions)]},
                    )
                else:
                    response = await client.get("/api/health")
                statuses[str(response.status_code)] += 1
                if response.status_code != 200:
                    errors[response.text[:200]] += 1
            except httpx.HTTPError as error:
                statuses[type(error).__name__] += 1
            durations.append(time.perf_counter() - started)

    started = time.perf_counter()
    await asyncio.gather(*(request(index) for index in range(count)))
    elapsed = time.perf_counter() - started
    durations.sort()
    result = {
        "test": label,
        "concurrency": concurrency,
        "requests": count,
        "seconds": round(elapsed, 2),
        "requests_per_second": round(count / elapsed, 2),
        "p50_ms": round(durations[len(durations) // 2] * 1000),
        "p95_ms": round(
            durations[min(len(durations) - 1, int(len(durations) * 0.95))] * 1000
        ),
        "max_ms": round(durations[-1] * 1000),
        "statuses": dict(statuses),
        "errors": dict(errors),
    }
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def run(url):
    async with httpx.AsyncClient(
        base_url=url,
        trust_env=False,
        timeout=120,
        limits=httpx.Limits(max_connections=100),
    ) as client:
        response = await client.get("/api/health")
        response.raise_for_status()
        results = []
        for concurrency in (1, 10, 50, 100):
            results.append(await batch(client, "HTTP health", concurrency, 500))
        response = await client.get("/api/health")
        response.raise_for_status()
        local = response.json().get("sql_backend") == "local"
        if not local and response.json().get("model") != "ready":
            print("Qwen не готов: тест генерации пропущен", flush=True)
            return results
        warmup = await client.post(
            "/api/query", json={"question": "Сколько всего студентов?"}
        )
        warmup.raise_for_status()
        count = 100 if local else 16
        stages = (1, 10, 25, 50, 100) if local else (1, 4, 8, 16)
        for concurrency in stages:
            results.append(
                await batch(
                    client,
                    "Templates + PostgreSQL" if local else "Qwen + PostgreSQL",
                    concurrency,
                    count,
                    model=True,
                )
            )
            if results[-1]["statuses"] != {"200": count}:
                break
        return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()
