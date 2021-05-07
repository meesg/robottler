from aioconsole import ainput
from types import SimpleNamespace
import asyncio
import json
import pathlib
import ssl
import sys
import websockets

gameState = None
board = None

async def consumer_handler(websocket, path):
    async for message in websocket:
        try:
            data = json.loads(message, object_hook=lambda d: SimpleNamespace(**d))
            if hasattr(data, "tileState"):
                print("here")
                global board
                board = data
                print(findHighestProducingSpot())
            if isinstance(data, list) and hasattr(data[0], "hexCorner"):
                addSettlementToBoard(data[0])
        except:
            pass
        # print(message) # clogs the STDOUT and leads to BlockingIOError: [Errno 11] after a while

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

def findCornerByCoordinates(x, y, z): 
    for corner in board.tileState.tileCorners:
        if corner.hexCorner.x == x and corner.hexCorner.y == y and corner.hexCorner.z == z:
            return corner
    return None

def restrictCorner(x, y, z):
    corner = findCornerByCoordinates(x, y, z)
    # print("Restricting: ({x}, {y}, {z})".format(x=x, y=y, z=z))
    if corner is None: return
    corner.restrictedStartingPlacement = True

# TODO: Fix bug because of which this function doesn't always complete
def addSettlementToBoard(newCorner):
    x = newCorner.hexCorner.x
    y = newCorner.hexCorner.y
    z = newCorner.hexCorner.z
    corner = findCornerByCoordinates(x, y, z)
    if corner is None: raise AttributeError("Corner with given coordinates doesn't exist within the board.")
    corner.owner = newCorner.owner
    
    if z == 0:
        restrictCorner(x, y - 1, 1)
        restrictCorner(x + 1, y - 1, 1)
        restrictCorner(x + 1, y - 2, 1)
    else:
        restrictCorner(x - 1, y + 1, 0)
        restrictCorner(x, y + 1, 0)
        restrictCorner(x - 1, y + 2, 0)
    print(findHighestProducingSpot())

# TODO: Store tiles in a smarter way to make this a O(1) function
def findTileByCoordinates(x, y):
    for tile in board.tileState.tiles:
        if tile.hexFace.x == x and tile.hexFace.y == y:
            return tile
    return None

def findProductionTileByCoordinates(x, y):
    tile = findTileByCoordinates(x, y)
    if tile is None: return 0
    if not hasattr(tile, '_diceProbability'): return 0
    return tile._diceProbability

def findHighestProducingSpot():
    x = y = z = 0
    high_prod = -1
    for corner in board.tileState.tileCorners:
        if corner.owner != 0 or corner.restrictedStartingPlacement is True: continue

        prod = findProductionTileByCoordinates(corner.hexCorner.x, corner.hexCorner.y)
        if corner.hexCorner.z == 0:
            prod += findProductionTileByCoordinates(corner.hexCorner.x, corner.hexCorner.y - 1)
            prod += findProductionTileByCoordinates(corner.hexCorner.x + 1, corner.hexCorner.y - 1)
        else:
            prod += findProductionTileByCoordinates(corner.hexCorner.x - 1, corner.hexCorner.y + 1)
            prod += findProductionTileByCoordinates(corner.hexCorner.x, corner.hexCorner.y + 1)
        if prod > high_prod:
            high_prod = prod
            x = corner.hexCorner.x
            y = corner.hexCorner.y
            z = corner.hexCorner.z
    return x, y, z

start_server = websockets.serve(handler, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
