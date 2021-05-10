from aioconsole import ainput
from types import SimpleNamespace
import asyncio
import json
import pathlib
import ssl
import sys
import websockets

from board import Board

player_color = 1 # TODO: find a way to find this procedurally in ingame lobbies, in standard bot games this works because you're always red (=1)
board = None
queue = None
turn_started = False

async def consumer_handler(websocket, path):
    async for message in websocket:
        try:
            data = json.loads(message, object_hook=lambda d: SimpleNamespace(**d))
            if hasattr(data, "tileState"): # Board information
                global board
                board = Board(data)
            elif hasattr(data, "currentTurnState"): # Game state information
                global turn_started
                if data.currentTurnPlayerColor == player_color and data.currentActionState == 1 and not turn_started:
                    print("Settlement time")
                    turn_started = True
                    settlement_index = findHighestProducingSpot()

                    buildSettlement(settlement_index)
                    board.own_settlements.append(settlement_index)
                    print(board.own_settlements)
                if data.currentTurnPlayerColor == player_color and data.currentActionState == 3:
                    print("Road time")
                    x = board.vertices[board.own_settlements[-1]].hexCorner.x
                    y = board.vertices[board.own_settlements[-1]].hexCorner.y
                    z = board.vertices[board.own_settlements[-1]].hexCorner.z
                    road_index = getRoadNextToSettlement(x, y, z)
                    buildRoad(road_index)
                if data.currentTurnPlayerColor != player_color:
                    turn_started = False # TODO: fix end turn check, this doesn't work when bot is last to place first settlement
            elif isinstance(data, list) and hasattr(data[0], "hexCorner"): # Settlement update (probably upgrading to a city works the same)
                addSettlementToBoard(data[0])
        except:
            pass

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
    for corner in board.vertices:
        if corner.hexCorner.x == x and corner.hexCorner.y == y and corner.hexCorner.z == z:
            return corner
    return None

def restrictCorner(x, y, z):
    corner = findCornerByCoordinates(x, y, z)
    if corner is None: return
    print("Restricting: ({x}, {y}, {z})".format(x=x, y=y, z=z))
    corner.restrictedStartingPlacement = True

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
    for tile in board.tiles:
        if tile.hexFace.x == x and tile.hexFace.y == y:
            return tile
    return None

def findProductionTileByCoordinates(x, y):
    tile = findTileByCoordinates(x, y)
    if tile is None: return 0
    if not hasattr(tile, '_diceProbability'): return 0
    return tile._diceProbability

def findVertexProduction(x, y, z):
    prod = findProductionTileByCoordinates(x, y)
    if z == 0:
        prod += findProductionTileByCoordinates(x, y - 1)
        prod += findProductionTileByCoordinates(x + 1, y - 1)
    else:
        prod += findProductionTileByCoordinates(x - 1, y + 1)
        prod += findProductionTileByCoordinates(x, y + 1)
    return prod

def findVertexProductionById(vertex_id):
    loc = board.vertices[vertex_id].hexCorner
    return findVertexProduction(loc.x, loc.y, loc.z)

# Loops over all hexcorners to find the highest producing spot
# where its still possible to build a settlement
def findHighestProducingSpot():
    i = high_index = -1
    high_prod = -1
    for i, corner in enumerate(board.vertices):
        if corner.owner != 0 or corner.restrictedStartingPlacement is True: continue

        prod = findVertexProduction(corner.hexCorner.x, corner.hexCorner.y, corner.hexCorner.z)
        if prod > high_prod:
            high_prod = prod
            high_index = i

    return high_index

def getRoadIndexByCoordinates(x, y, z):
    i = 0
    for edge in board.edges:
        if edge.hexEdge.x == x and edge.hexEdge.y == y and edge.hexEdge.z == z:
            return i
        i += 1
    return None

# x, y, z: settlement coordinates
# returns road index
def getRoadNextToSettlement(x, y, z):
    if z == 0:
        return getRoadIndexByCoordinates(x, y, 0)
    if z == 1:
        return getRoadIndexByCoordinates(x, y, 2)
    return None

def findNextSettlement():
    candidates = []

    for settlement_index in board.own_settlements:
        candidates.append(findNeighboursByDegree(None, settlement_index, 2))
    
    high_vertex_index = -1
    high_prod = -1
    for vertex_index in candidates:
        prod = findVertexProductionById(vertex_index)
        if prod > high_prod:
            high_vertex_index = vertex_index
            high_prod = prod
            
    return high_vertex_index
        

def findNeighboursByDegree(prev_vertex_index, vertex_index, degree):
    print("findNeighboursByDegree({0}, {1}, {2})".format(prev_vertex_index, vertex_index, degree))
    if degree <= 0: return vertex_index

    neighbours = []
    for entry in board.adjacency_map[vertex_index]:
        vertex = board.vertices[entry["vertex_index"]]
        edge = board.edges[entry["edge_index"]]
        if prev_vertex_index != entry["vertex_index"] and vertex.owner == 0 and edge.owner == 0:
            neighbours.append(findNeighboursByDegree(vertex_index, entry["vertex_index"], degree - 1))
        
    return neighbours

def buildRoad(road_index):
    send({ "action": 0, "data": road_index })

def buildSettlement(settlement_index):
    send({ "action": 1, "data": settlement_index })

def buildCity(settlement_index):
    send({ "action": 2, "data": settlement_index })

def buyDevCard(settlement_index):
    send({ "action": 3 })

def throwDice(settlement_index):
    send({ "action": 4 })

def passTurn():
    send({ "action": 5 })

def send(data):
    dataInJson = json.dumps(data)
    queue.put_nowait(dataInJson)

queue = asyncio.Queue()
start_server = websockets.serve(handler, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
