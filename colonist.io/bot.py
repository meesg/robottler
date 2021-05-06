import asyncio
import pathlib
import ssl
import websockets
import sys
from aioconsole import ainput

async def consumer_handler(websocket, path):
    async for message in websocket:
        print(message) # clogs the STDOUT and leads to BlockingIOError: [Errno 11] after a while

async def producer_handler(websocket, path):
    while True:
        message = await ainput()
        await websocket.send(message)

async def handler(websocket, path):
    consumer_task = asyncio.ensure_future(
        consumer_handler(websocket, path))
    producer_task = asyncio.ensure_future(
        producer_handler(websocket, path))
    done, pending = await asyncio.wait(
        [consumer_task, producer_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

start_server = websockets.serve(handler, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
