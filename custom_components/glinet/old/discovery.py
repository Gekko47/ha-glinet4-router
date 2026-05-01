import asyncio
import ipaddress
import socket


GLINET_DEFAULT_PORT = 80


async def _check_host(ip: str) -> bool:
    """Check if GL.iNet likely exists on host."""
    try:
        reader, writer = await asyncio.open_connection(ip, GLINET_DEFAULT_PORT)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def discover_glinet_router(subnet: str):
    """
    Scan subnet for GL.iNet router.
    Returns first candidate IP or None.
    """
    network = ipaddress.ip_network(subnet, strict=False)

    tasks = []
    for ip in network.hosts():
        tasks.append(_check_host(str(ip)))

        # avoid overload
        if len(tasks) >= 50:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, ok in enumerate(results):
                if ok:
                    return str(list(network.hosts())[i])
            tasks = []

    return None