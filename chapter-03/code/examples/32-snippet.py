import asyncio

async def fetch_answer(delay: float) -> str:
    await asyncio.sleep(delay)          # pretend this is a network call
    return f"answer after {delay}s"

async def main():
    results = await asyncio.gather(fetch_answer(1), fetch_answer(1), fetch_answer(1))
    print(results)                      # all three finish in ~1 second, not 3

asyncio.run(main())
