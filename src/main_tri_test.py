import asyncio

from sim_exec import exec_tri
from tri_stream import TriStream
from utils.logger import log_tri


async def calc():
    ts = TriStream()
    asyncio.create_task(ts.start())

    while True:
        # wait until all books are loaded
        if None in ts.books.values():
            await asyncio.sleep(0.01)
            continue

        (ab_bid, ab_ask) = ts.books["ab"]
        (bc_bid, bc_ask) = ts.books["bc"]
        (ac_bid, ac_ask) = ts.books["ac"]

        start = 1.0  # 1 USDC
        btc = start / ab_ask
        eth = btc / bc_ask
        final = eth * ac_bid

        edge = (final - start) * 100

        final_sim, exec_edge = exec_tri(ab_ask, bc_ask, ac_bid)

        # log -> tri.csv
        log_tri(ab_ask, bc_ask, ac_bid, edge, final_sim, exec_edge)

        print(f"EDGE_USDC: {edge:.4f}% | SIM: {exec_edge:.4f}% | end: {final_sim}")

        await asyncio.sleep(0.03)


if __name__ == "__main__":
    asyncio.run(calc())
