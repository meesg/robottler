from aioconsole import ainput
from types import SimpleNamespace
import asyncio
import json
import pathlib
import ssl
import sys
import websockets

playerColor = 1 # TODO: find a way to find this procedurally in ingame lobbies, in standard botgames you're always red (=1)
gameState = None
board = None
queue = None
lastX = lastY = lastZ = None # TODO: so many things wrong with this, clean this
turnStarted = False

async def consumer_handler(websocket, path):
    async for message in websocket:
        try:
            data = json.loads(message, object_hook=lambda d: SimpleNamespace(**d))
            if hasattr(data, "tileState"): # Board information
                global board
                board = data
            elif hasattr(data, "currentTurnState"): # Game state information
                global turnStarted
                if data.currentTurnPlayerColor == playerColor and data.currentActionState == 1 and not turnStarted:
                    print("Settlement time")
                    turnStarted = True
                    settlement_index = findHighestProducingSpot()
                    buildSettlement(settlement_index)
                if data.currentTurnPlayerColor == playerColor and data.currentActionState == 3:
                    print("Road time")
                    road_index = getRoadNextToSettlement(lastX, lastY, lastZ)
                    buildRoad(road_index)
                if data.currentTurnPlayerColor != playerColor:
                    turnStarted = False # TODO: fix end turn check, this doesn't work when bot is last to place first settlement
            elif isinstance(data, list) and hasattr(data[0], "hexCorner"): # Settlement update (probably upgrading to a city works the same)
                addSettlementToBoard(data[0])
        except:
            pass
        # print(message) # clogs the STDOUT and leads to BlockingIOError: [Errno 11] after a while

async def producer_handler(websocket, path):
    while True:
        message = await queue.get()
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
    if corner is None: return
    print("Restricting: ({x}, {y}, {z})".format(x=x, y=y, z=z))
    corner.restrictedStartingPlacement = True

# TODO: Fix bug because of which this function doesn't always complete
def addSettlementToBoard(newCorner):
    x = newCorner.hexCorner.x
    y = newCorner.hexCorner.y
    z = newCorner.hexCorner.z
    print("Adding settlement: ({x}, {y}, {z})".format(x=x, y=y, z=z))
    corner = findCornerByCoordinates(x, y, z)
    if corner is None: raise ValueError("Given coordinates don't exist on the board.")
    corner.owner = newCorner.owner
    
    if z == 0:
        restrictCorner(x, y - 1, 1)
        restrictCorner(x + 1, y - 1, 1)
        restrictCorner(x + 1, y - 2, 1)
    else:
        restrictCorner(x - 1, y + 1, 0)
        restrictCorner(x, y + 1, 0)
        restrictCorner(x - 1, y + 2, 0)

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

# Loops over all hexcorners to find the highest producing spot
# where its still possible to build a settlement
def findHighestProducingSpot():
    x = y = z = 0
    i = high_index = -1
    high_prod = -1
    for corner in board.tileState.tileCorners:
        i += 1
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
            high_index = i

    # Store coordinates to create road with later, yeahhhhhhh uhhhmmm
    global lastX
    global lastY
    global lastZ
    lastX = x
    lastY = y
    lastZ = z

    return high_index

def getRoadIndexByCoordinates(x, y, z):
    i = 0
    for edge in board.tileState.tileEdges:
        if edge.hexEdge.x == x and edge.hexEdge.y == y and edge.hexEdge.z == z:
            return i
        i += 1
    return None

# x, y, z: settlement coordinates
# returns road index
def getRoadNextToSettlement(x, y, z):
    print(z)
    if z == 0:
        return getRoadIndexByCoordinates(x, y, 0)
    if z == 1:
        return getRoadIndexByCoordinates(x, y, 2)
    return None

def buildSettlement(settlementIndex):
    send({ "action": 1, "data": settlementIndex })

def buildRoad(roadIndex):
    send({ "action": 0, "data": roadIndex })

def passTurn():
    send({ "action": 5, "data": True })

def send(data):
    dataInJson = json.dumps(data)
    queue.put_nowait(dataInJson)

queue = asyncio.Queue()
start_server = websockets.serve(handler, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
