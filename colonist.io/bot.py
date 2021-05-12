from enum import Enum
from types import SimpleNamespace
import asyncio
import copy
import json
import websockets

from board import Board
from resources import Resources

# TODO: find a way to find this procedurally in ingame lobbies,
# in standard bot games this works because you're always red (=1)
PLAYER_COLOR = 1
BOARD = None
QUEUE = None

NEXT_SETTLEMENT = None  # TODO: clean


class GameState(Enum):
    SETUP_SETTLEMENT = 0
    SETUP_ROAD = 1
    EXPANDING = 2
    CITIES = 3
    DEV_CARDS = 4


road_cards = {Resources.WOOD: 1, Resources.BRICK: 1}
settlement_cards = {Resources.WOOD: 1, Resources.BRICK: 1,
                    Resources.SHEEP: 1, Resources.WHEAT: 1}
city_cards = {Resources.WHEAT: 2, Resources.ORE: 3}
dev_card_cards = {Resources.SHEEP: 1, Resources.WHEAT: 1, Resources.ORE: 1}

GAME_STATE = GameState.SETUP_SETTLEMENT


async def consumer_handler(websocket, path):
    async for message in websocket:
        try:
            data = json.loads(
                message, object_hook=lambda d: SimpleNamespace(**d))
            if hasattr(data, "tileState"):  # Board information
                global BOARD
                BOARD = Board(data)
            elif hasattr(data, "currentTurnState"):  # Game state information
                global GAME_STATE

                if data.currentTurnPlayerColor == PLAYER_COLOR:
                    # need to be outside the currentTurnState ifs,
                    # because it can happen in both turnstate 1 and 2
                    if data.currentActionState == 22:
                        print("We have to place robber!")
                        new_robber_tile_index = find_new_robber_tile()
                        print("New robber tile index : {0}".format(
                            new_robber_tile_index))
                        move_robber(new_robber_tile_index)
                    if data.currentTurnState == 0:
                        if data.currentActionState == 1 and \
                           GAME_STATE == GameState.SETUP_SETTLEMENT:
                            print("Building settlement")
                            settlement_index = find_highest_producing_vertex()

                            build_settlement(settlement_index)
                            BOARD.own_settlements.append(settlement_index)

                            GAME_STATE = GameState.SETUP_ROAD
                        if data.currentActionState == 3 and GAME_STATE == GameState.SETUP_ROAD:
                            print("Building road")
                            road_index = find_next_road(
                                BOARD.own_settlements[-1], True)
                            build_road(road_index)

                            if len(BOARD.own_settlements) < 2:
                                GAME_STATE = GameState.SETUP_SETTLEMENT
                            else:
                                GAME_STATE = GameState.EXPANDING
                    if data.currentTurnState == 1:
                        if data.currentActionState == 0:
                            throw_dice()
                    if data.currentTurnState == 2:
                        next_road = find_next_road(None, False)
                        if next_road is not None:
                            if distance_from_cards(road_cards, BOARD.resources) == 0:
                                build_road(next_road)
                        elif distance_from_cards(settlement_cards, BOARD.resources) == 0:
                            build_settlement(NEXT_SETTLEMENT)
                        pass_turn()
            # TODO: remember the player next to tile we place robber on
            # so we can do the logic on the turn logic package
            elif hasattr(data, "allowableActionState"):
                if data.allowableActionState == 23:
                    print("stealing time")
                    rob_player(data.playersToSelect[0])
            elif hasattr(data, "selectCardFormat"):
                print("disarding time")
                cards = pick_cards_to_discard(
                    data.selectCardFormat.amountOfCardsToSelect)
                discard_cards(cards)
            elif hasattr(data, "givingPlayer"):  # Trade information
                if data.givingPlayer == PLAYER_COLOR:
                    for card in data.givingCards:
                        BOARD.resources[Resources(card)] -= 1
                    for card in data.receivingCards:
                        BOARD.resources[Resources(card)] += 1
                if data.receivingPlayer == PLAYER_COLOR:
                    for card in data.givingCards:
                        BOARD.resources[Resources(card)] += 1
                    for card in data.receivingCards:
                        BOARD.resources[Resources(card)] -= 1
            elif hasattr(data, "offeredResources"):  # Active trade offer
                # Check if we're allowed to take this trade and have to respond
                for player_actions in data.actions:
                    if player_actions.player == PLAYER_COLOR:
                        if len(player_actions.allowedTradeActions) > 0:
                            break
                        else:
                            return
                # Respond to trade offer
                if is_favourable_trade(data):
                    accept_trade(data.id)
                else:
                    reject_trade(data.id)
            # Settlement update (probably upgrading to a city works the same)
            elif isinstance(data, list) and hasattr(data[0], "hexCorner"):
                update_vertex(data[0])
            elif isinstance(data, list) and hasattr(data[0], "hexEdge"):
                update_edge(data[0])
            # Cards being handed out
            elif isinstance(data, list) and hasattr(data[0], "owner"):
                for entry in data:
                    if entry.owner == PLAYER_COLOR:
                        # TODO: fix for cities, probably can just increment with distribitionType
                        BOARD.resources[Resources(entry.card)] += 1
            # Robber move information
            elif isinstance(data, list) and hasattr(data[0], "tilePieceTypes"):
                new_robber_tile = data[1]
                loc = new_robber_tile.hexFace
                BOARD.robber_tile = BOARD.find_tile_index_by_coordinates(
                    loc.x, loc.y)
                print("New robber_tile: {0}".format(BOARD.robber_tile))
        except:
            pass


async def producer_handler(websocket, path):
    while True:
        message = await QUEUE.get()
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


def find_vertex_by_coordinates(x, y, z):
    for corner in BOARD.vertices:
        if corner.hexCorner.x == x and corner.hexCorner.y == y and corner.hexCorner.z == z:
            return corner
    return None


def find_edge_by_coordinates(x, y, z):
    for edge in BOARD.edges:
        if edge.hexEdge.x == x and edge.hexEdge.y == y and edge.hexEdge.z == z:
            return edge
    return None


def update_vertex(new_vertex_info):
    loc = new_vertex_info.hexCorner
    vertex_index = BOARD.find_vertex_index_by_coordinates(loc.x, loc.y, loc.z)
    board_vertex = find_vertex_by_coordinates(loc.x, loc.y, loc.z)

    if board_vertex is None:
        raise ValueError("Given coordinates don't exist on the board.")

    board_vertex.owner = new_vertex_info.owner
    board_vertex.buildingType = new_vertex_info.buildingType

    if board_vertex.owner == 1:
        tiles = BOARD.vertex_tiles[vertex_index]
        for tile in tiles:
            BOARD.own_production[tile.tileType] += tile._diceProbability

    neighbours = BOARD.adjacency_map[vertex_index]

    for neighbour in neighbours:
        BOARD.vertices[neighbour["vertex_index"]].restrictedStartingPlacement = True


def update_edge(road):
    edge = find_edge_by_coordinates(
        road.hexEdge.x, road.hexEdge.y, road.hexEdge.z)
    edge.owner = road.owner

# TODO: Store tiles in a smarter way to make this a O(1) function


def find_tile_by_coordinates(x, y):
    for tile in BOARD.tiles:
        if tile.hexFace.x == x and tile.hexFace.y == y:
            return tile
    return None


def find_production_tile_by_coordinates(x, y):
    tile = find_tile_by_coordinates(x, y)
    if tile is None:
        return 0
    if not hasattr(tile, '_diceProbability'):
        return 0
    return tile._diceProbability


def find_vertex_production(x, y, z):
    # print("findVertexProduction({0}, {1}, {2})".format(x, y, z))
    prod = find_production_tile_by_coordinates(x, y)
    if z == 0:
        prod += find_production_tile_by_coordinates(x, y - 1)
        prod += find_production_tile_by_coordinates(x + 1, y - 1)
    else:
        prod += find_production_tile_by_coordinates(x - 1, y + 1)
        prod += find_production_tile_by_coordinates(x, y + 1)
    return prod


def find_vertex_production_by_id(vertex_id):
    # print("findVertexProductionById({0})".format(vertex_id))
    loc = BOARD.vertices[vertex_id].hexCorner
    return find_vertex_production(loc.x, loc.y, loc.z)

# Loops over all hexcorners to find the highest producing spot
# where its still possible to build a settlement


def find_highest_producing_vertex():
    i = high_index = -1
    high_prod = -1
    for i, corner in enumerate(BOARD.vertices):
        if corner.owner != 0 or corner.restrictedStartingPlacement is True:
            continue

        prod = find_vertex_production(
            corner.hexCorner.x, corner.hexCorner.y, corner.hexCorner.z)
        if prod > high_prod:
            high_prod = prod
            high_index = i

    return high_index


def get_road_index_by_coordinates(x, y, z):
    i = 0
    for edge in BOARD.edges:
        if edge.hexEdge.x == x and edge.hexEdge.y == y and edge.hexEdge.z == z:
            return i
        i += 1
    return None

# x, y, z: settlement coordinates
# returns road index


def get_road_next_to_settlement(x, y, z):
    if z == 0:
        return get_road_index_by_coordinates(x, y, 0)
    if z == 1:
        return get_road_index_by_coordinates(x, y, 2)
    return None


def find_next_road(settlement_index, is_setup):
    candidates = []

    if settlement_index is None:
        for index in BOARD.own_settlements:
            candidates.extend(find_settlement_spots(None, index, [], 2))
    else:
        candidates.extend(find_settlement_spots(None, settlement_index, [], 2))

    high_vertex_index = -1
    high_prod = -1
    high_path = None
    for entry in candidates:
        vertex_index = entry["vertex_index"]

        prod = find_vertex_production_by_id(vertex_index)
        if prod > high_prod and (not is_setup or prod <= 7):
            high_vertex_index = vertex_index
            high_prod = prod
            high_path = entry["path"]

    global NEXT_SETTLEMENT
    NEXT_SETTLEMENT = high_vertex_index
    for edge_index in high_path:
        if BOARD.edges[edge_index].owner == 0:
            return edge_index
    return None


def find_settlement_spots(prev_vertex_index, vertex_index, path, degree):
    if degree <= 0:
        vert = BOARD.vertices[vertex_index]
        if vert.owner == 0 and not vert.restrictedStartingPlacement:
            return [{"vertex_index": vertex_index, "path": path}]
        else:
            return []

    candidates = []
    for entry in BOARD.adjacency_map[vertex_index]:
        vertex = BOARD.vertices[entry["vertex_index"]]
        edge = BOARD.edges[entry["edge_index"]]
        if prev_vertex_index != entry["vertex_index"] and \
           (vertex.owner == 0 or vertex.owner == PLAYER_COLOR) and \
           (edge.owner == 0 or edge.owner == PLAYER_COLOR):
            new_path = []
            new_path.extend(path)
            new_path.append((entry["edge_index"]))
            candidates.extend(find_settlement_spots(
                vertex_index, entry["vertex_index"], new_path, degree - 1))

    return candidates


def distance_from_cards(needed, cards):
    dist = 0
    for resource, amount in needed.items():
        dist += max(0, amount - cards[resource])
    return dist


def distance_from_objective(cards):
    if GAME_STATE == GameState.EXPANDING:
        if find_next_road(None, False) is not None:
            return distance_from_cards(road_cards, cards)
        else:
            return distance_from_cards(settlement_cards, cards)
    if GAME_STATE == GameState.CITIES:
        return distance_from_cards(city_cards, cards)
    if GAME_STATE == GameState.DEV_CARDS:
        return distance_from_cards(dev_card_cards, cards)


def is_favourable_trade(data):
    resources_after_trade = copy.deepcopy(BOARD.resources)
    for card in data.offeredResources.cards:
        resources_after_trade[Resources(card)] += 1
    for card in data.wantedResources.cards:
        resources_after_trade[Resources(card)] -= 1
    return distance_from_objective(resources_after_trade) < distance_from_objective(BOARD.resources)


def find_new_robber_tile():
    high_index = -1
    high_block = -1

    for i, tile in enumerate(BOARD.tiles):
        if BOARD.robber_tile == i:
            continue
        if tile.tileType == 0:
            continue  # desert tile doesn't have the _diceProbability attribute

        block = 0
        for vertex_index in BOARD.tile_vertices[i]:
            vertex = BOARD.vertices[vertex_index]

            if vertex.owner == PLAYER_COLOR:
                break
            if vertex.owner != 0:
                block += tile._diceProbability * vertex.buildingType
        else:  # only runs if execution isnt broken during loop
            if block > high_block:
                high_block = block
                high_index = i

    return high_index


def pick_cards_to_discard(amount):
    next_cards = None

    if GAME_STATE == GameState.EXPANDING:
        if find_next_road(None, False) is not None:
            next_cards = road_cards
        else:
            next_cards = settlement_cards
    elif GAME_STATE == GameState.CITIES:
        next_cards = city_cards
    elif GAME_STATE == GameState.DEV_CARDS:
        next_cards = dev_card_cards

    non_discarded_cards = copy.deepcopy(BOARD.resources)
    discarded_cards = []
    extra_cards = True
    # 1. round robin cards not necessary for next buy
    # 2. round robin cards necessary for next buy
    while len(discarded_cards) < amount:
        extra_card_found = False
        for resource in Resources:
            if extra_cards:
                if (resource not in next_cards or \
                    non_discarded_cards[resource] > next_cards[resource]) and \
                   non_discarded_cards[resource] > 0:
                    discarded_cards.append(resource.value)
                    non_discarded_cards[resource] -= 1
                    extra_card_found = True
            else:
                if non_discarded_cards[resource] > 0:
                    discarded_cards.append(resource.value)
                    non_discarded_cards[resource] -= 1

            if len(discarded_cards) == amount:
                break
        if extra_card_found is False:
            extra_cards = False
    return discarded_cards


def build_road(road_index):
    send({"action": 0, "data": road_index})


def build_settlement(settlement_index):
    send({"action": 1, "data": settlement_index})


def build_city(settlement_index):
    send({"action": 2, "data": settlement_index})


def buy_dev_card():
    send({"action": 3})


def throw_dice():
    send({"action": 4})


def pass_turn():
    send({"action": 5})


def accept_trade(trade_id):
    send({"action": 6, "data": trade_id})


def reject_trade(trade_id):
    send({"action": 7, "data": trade_id})


def move_robber(tile_index):
    send({"action": 8, "data": tile_index})


def rob_player(player):
    send({"action": 9, "data": player})


def discard_cards(cards):
    send({"action": 10, "data": cards})


def send(data):
    data_in_json = json.dumps(data)
    QUEUE.put_nowait(data_in_json)


QUEUE = asyncio.Queue()
start_server = websockets.serve(handler, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
