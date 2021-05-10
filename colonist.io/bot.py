from aioconsole import ainput
from types import SimpleNamespace
from enum import Enum
import asyncio
import json
import pathlib
import ssl
import sys
import websockets

from board import Board
from resources import Resources

player_color = 1 # TODO: find a way to find this procedurally in ingame lobbies, in standard bot games this works because you're always red (=1)
board = None
queue = None

class GameState(Enum):
    SETUP_SETTLEMENT = 0
    SETUP_ROAD = 1
    EXPANDING = 2
    CITIES = 3
    DEV_CARDS = 4

game_state = GameState.SETUP_SETTLEMENT

async def consumer_handler(websocket, path):
    async for message in websocket:
        try:
            data = json.loads(message, object_hook=lambda d: SimpleNamespace(**d))
            if hasattr(data, "tileState"): # Board information
                global board
                board = Board(data)
            elif hasattr(data, "currentTurnState"): # Game state information
                global game_state
                if data.currentTurnPlayerColor == player_color:
                    if data.currentTurnState == 0:
                        if data.currentActionState == 1 and game_state == GameState.SETUP_SETTLEMENT:
                            print("Building settlement")
                            settlement_index = findHighestProducingSpot()

                            buildSettlement(settlement_index)
                            board.own_settlements.append(settlement_index)
                            
                            game_state = GameState.SETUP_ROAD
                        if data.currentActionState == 3 and game_state == GameState.SETUP_ROAD:
                            print("Building road")
                            road_index = findNextRoad(board.own_settlements[-1], True)
                            buildRoad(road_index)

                            if len(board.own_settlements) < 2:
                                game_state = GameState.SETUP_SETTLEMENT
                            else:
                                game_state = GameState.EXPANDING
                    if data.currentTurnState == 1:
                        if data.currentActionState == 0:
                            throwDice()
                    if data.currentTurnState == 2:
                        print("My turn!")
                        next_road = findNextRoad(None, False)
                        print(next_road)
                        if next_road != None:
                            if board.resources[Resources.WOOD] > 0 and board.resources[Resources.BRICK] > 0:
                                buildRoad(next_road)
                        # passTurn()
            elif hasattr(data, "givingPlayer"): # Trades
                if (data.givingPlayer == player_color):
                    for card in data.givingCards:
                        board.resources[Resources(card)] -= 1
                    for card in data.receivingCards:
                        board.resources[Resources(card)] += 1
                if (data.receivingPlayer == player_color):
                    for card in data.givingCards:
                        board.resources[Resources(card)] += 1
                    for card in data.receivingCards:
                        board.resources[Resources(card)] -= 1
            elif isinstance(data, list) and hasattr(data[0], "hexCorner"): # Settlement update (probably upgrading to a city works the same)
                addSettlementToBoard(data[0])
            elif isinstance(data, list) and hasattr(data[0], "hexEdge"):
                addRoadToBoard(data[0])
            elif isinstance(data, list) and hasattr(data[0], "owner"): # Cards being handed out
                for entry in data:
                    print(entry)
                    if entry.owner == player_color: 
                        board.resources[Resources(entry.card)] += 1 # TODO: fix for cities, probably can just increment with distribitionType
                pass
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

def findEdgeByCoordinates(x, y, z): 
    for edge in board.edges:
        if edge.hexEdge.x == x and edge.hexEdge.y == y and edge.hexEdge.z == z:
            return edge
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

def addRoadToBoard(road):
    edge = findEdgeByCoordinates(road.hexEdge.x, road.hexEdge.y, road.hexEdge.z)
    edge.owner = road.owner

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
    # print("findVertexProduction({0}, {1}, {2})".format(x, y, z))
    prod = findProductionTileByCoordinates(x, y)
    if z == 0:
        prod += findProductionTileByCoordinates(x, y - 1)
        prod += findProductionTileByCoordinates(x + 1, y - 1)
    else:
        prod += findProductionTileByCoordinates(x - 1, y + 1)
        prod += findProductionTileByCoordinates(x, y + 1)
    return prod

def findVertexProductionById(vertex_id):
    # print("findVertexProductionById({0})".format(vertex_id))
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

def findNextRoad(settlement_index, is_setup):
    candidates = []

    if settlement_index == None:
        for index in board.own_settlements:
            candidates.extend(findSettlementSpots(None, index, [], 2))
    else:
        candidates.extend(findSettlementSpots(None, settlement_index, [], 2))

    high_vertex_index = -1
    high_prod = -1
    high_path = None
    for entry in candidates:
        vertex_index = entry["vertex_index"]

        prod = findVertexProductionById(vertex_index)
        if prod > high_prod and (not is_setup or prod <= 7):
            high_vertex_index = vertex_index
            high_prod = prod
            high_path = entry["path"]

    for edge_index in high_path:
        if board.edges[edge_index].owner == 0:
            return edge_index
    return None
        

def findSettlementSpots(prev_vertex_index, vertex_index, path, degree):
    # print("findSettlementSpots({0}, {1}, {2}, {3})".format(prev_vertex_index, vertex_index, path, degree))
    if degree <= 0: 
        vert = board.vertices[vertex_index]
        if vert.owner == 0 and not vert.restrictedStartingPlacement:
            return [{ "vertex_index": vertex_index, "path": path }]
        else:
            return []

    candidates = []
    for entry in board.adjacency_map[vertex_index]:
        vertex = board.vertices[entry["vertex_index"]]
        edge = board.edges[entry["edge_index"]]
        if prev_vertex_index != entry["vertex_index"] and \
           (vertex.owner == 0 or vertex.owner == player_color) and \
           (edge.owner == 0 or edge.owner == player_color):
            new_path = []
            new_path.extend(path)
            new_path.append((entry["edge_index"]))
            candidates.extend(findSettlementSpots(vertex_index, entry["vertex_index"], new_path, degree - 1))
    
    return candidates

def buildRoad(road_index):
    send({ "action": 0, "data": road_index })

def buildSettlement(settlement_index):
    send({ "action": 1, "data": settlement_index })

def buildCity(settlement_index):
    send({ "action": 2, "data": settlement_index })

def buyDevCard():
    send({ "action": 3 })

def throwDice():
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
