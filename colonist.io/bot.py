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

class GameState(Enum):
    SETUP_SETTLEMENT = 0
    SETUP_ROAD = 1
    EXPANDING = 2
    CITIES = 3
    DEV_CARDS = 4

class PurchaseType(Enum):
    ROAD = 0
    SETTLEMENT = 1
    CITY = 2
    DEV_CARD = 3

cards_needed = {PurchaseType.ROAD:       {Resources.WOOD: 1, Resources.BRICK: 1},
                PurchaseType.SETTLEMENT: {Resources.WOOD: 1, Resources.BRICK: 1,
                                   Resources.SHEEP: 1, Resources.WHEAT: 1},
                PurchaseType.CITY:       {Resources.WHEAT: 2, Resources.ORE: 3},
                PurchaseType.DEV_CARD:   {Resources.SHEEP: 1, Resources.WHEAT: 1, Resources.ORE: 1}}

GAME_STATE = GameState.SETUP_SETTLEMENT

NEXT_ROAD = None
NEXT_SETTLEMENT = None  # TODO: clean
NEXT_PURCHASE = PurchaseType.ROAD
STARTED_TRADE = False

async def consumer_handler(websocket, _path):
    async for message in websocket:
        try:
            data = json.loads(
                message, object_hook=lambda d: SimpleNamespace(**d))
            if hasattr(data, "tileState"):  # Board information
                global BOARD
                BOARD = Board(data)
            elif hasattr(data, "currentTurnState"):  # Game state information
                global GAME_STATE
                global NEXT_PURCHASE

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

                            GAME_STATE = GameState.SETUP_ROAD
                        if data.currentActionState == 3 and GAME_STATE == GameState.SETUP_ROAD:
                            print("Building road")
                            road_index = find_next_road(BOARD.own_settlements[-1], True)
                            if road_index == None:
                                print("road_index == None")
                                road_index = BOARD.adjacency_map[BOARD.own_settlements[-1]][0]["edge_id"]
                            build_road(road_index)

                            if len(BOARD.own_settlements) < 2:
                                GAME_STATE = GameState.SETUP_SETTLEMENT
                            else:
                                GAME_STATE = GameState.EXPANDING
                    if data.currentTurnState == 1:
                        if data.currentActionState == 0:
                            throw_dice()
                    if data.currentTurnState == 2:
                        print("cards : {0}".format(cards_needed))
                        NEXT_PURCHASE = calculate_next_purchase()
                        print("NEXT_PURCHASE: {0}".format(NEXT_PURCHASE))
                        
                        print("cards[NEXT_PURCHASE] : {0}".format(cards_needed[NEXT_PURCHASE]))

                        if distance_from_cards(cards_needed[NEXT_PURCHASE], BOARD.resources) > 0:
                            trade_with_bank()
                        if distance_from_cards(cards_needed[NEXT_PURCHASE], BOARD.resources) == 0:
                            if NEXT_PURCHASE == PurchaseType.ROAD:
                                build_road(find_next_road(None, False))
                            if NEXT_PURCHASE == PurchaseType.SETTLEMENT:
                                build_settlement(NEXT_SETTLEMENT)
                            if NEXT_PURCHASE == PurchaseType.CITY:
                                build_city(BOARD.own_settlements[0])
                            if NEXT_PURCHASE == PurchaseType.DEV_CARD:
                                buy_dev_card()

                        # next_road = find_next_road(None, False)
                        # if next_road is not None:
                        #     needed_cards = cards[PurchaseType.ROAD]
                        #     if distance_from_cards(needed_cards, BOARD.resources) == 0:
                        #         build_road(next_road)
                        # elif distance_from_cards(cards[PurchaseType.SETTLEMENT], BOARD.resources) == 0:
                        #     build_settlement(NEXT_SETTLEMENT)
                        if not STARTED_TRADE:
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
                NEXT_PURCHASE = calculate_next_purchase()
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


async def producer_handler(websocket, _path):
    while True:
        message = await QUEUE.get()
        await websocket.send(message)


async def handler(websocket, path):
    consumer_task = asyncio.ensure_future(
        consumer_handler(websocket, path))
    producer_task = asyncio.ensure_future(
        producer_handler(websocket, path))
    _done, pending = await asyncio.wait(
        [consumer_task, producer_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()


def update_vertex(new_vertex_info):
    print("update_vertex")

    loc = new_vertex_info.hexCorner
    vertex_index = BOARD.find_vertex_index_by_coordinates(loc.x, loc.y, loc.z)
    vertex = BOARD.vertices[vertex_index]

    if vertex is None:
        raise ValueError("Given coordinates don't exist on the board.")

    vertex.owner = new_vertex_info.owner
    vertex.buildingType = new_vertex_info.buildingType

    if vertex.owner == 1:
        if vertex.buildingType == 1:
            BOARD.own_settlements.append(vertex_index)
        if vertex.buildingType == 2:
            BOARD.own_settlements.remove(vertex_index)
            BOARD.own_cities.append(vertex_index)

        tiles = BOARD.vertex_tiles[vertex_index]
        for tile_index in tiles:
            tile = BOARD.tiles[tile_index]
            if hasattr(tile, "_diceProbability"):
                BOARD.own_production[Resources(tile.tileType)] += tile._diceProbability

    neighbours = BOARD.adjacency_map[vertex_index]
    for neighbour in neighbours:
        print("Restricting neighbour: {0}".format(neighbour["vertex_index"]))
        BOARD.vertices[neighbour["vertex_index"]].restrictedStartingPlacement = True


def update_edge(new_edge_info):
    loc = new_edge_info.hexEdge
    edge_index = BOARD.find_edge_index_by_coordinates(loc.x, loc.y, loc.z)
    BOARD.edges[edge_index].owner = new_edge_info.owner

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


def find_highest_producing_vertex():
    """ Loops over all vertices to find the highest producing spot
    where its still possible to build a settlement
    """

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

def calc_missing_cards(needed, own_cards):
    dist = 0
    missing_cards = {}
    for resource, amount in needed.items():
        diff = max(0, amount - own_cards[resource])
        dist += diff
        if diff > 0:
            missing_cards[resource] = diff
    return dist, missing_cards

def distance_from_cards(needed, own_cards):
    dist = 0
    for resource, amount in needed.items():
        dist += max(0, amount - own_cards[resource])

    return dist

def is_favourable_trade(data):
    resources_after_trade = copy.deepcopy(BOARD.resources)
    for card in data.offeredResources.cards:
        resources_after_trade[Resources(card)] += 1
    for card in data.wantedResources.cards:
        resources_after_trade[Resources(card)] -= 1
    needed = cards_needed[calculate_next_purchase()]
    return distance_from_cards(needed, resources_after_trade) < distance_from_cards(needed, BOARD.resources)


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

def trade_with_bank():
    print("trade with bank")

    if distance_from_cards(cards_needed[NEXT_PURCHASE], BOARD.resources) == 0:
        return

    extra_resources = copy.deepcopy(BOARD.resources)
    print(cards_needed[NEXT_PURCHASE])
    for resource, amount in cards_needed[NEXT_PURCHASE].items():
        extra_resources[resource] -= amount
    print("extra_resources: {0}".format(extra_resources))
    
    dist, missing = calc_missing_cards(cards_needed[NEXT_PURCHASE], BOARD.resources)
    print("dist: {0}".format(dist))
    print("missing: {0}".format(missing))

    print(list(missing)[0].value)
    
    traded = True
    while traded:
        traded = False
        for resource in Resources:
            print("Extra {0} : {1}".format(resource, extra_resources[resource]))
            if extra_resources[resource] >= 4:
                print("Starting 4:1 trade")

                offered = [resource.value for x in range(4)]
                wanted = [list(missing)[0].value]

                print("offered : {0}".format(offered))
                print("wanted : {0}".format(wanted))

                create_trade(offered, wanted)
                global STARTED_TRADE
                STARTED_TRADE = True

                extra_resources[resource] -= 4
                missing[list(missing)[0]] -= 1

                if missing[list(missing)[0]] <= 0:
                    del missing[list(missing)[0]]
                if len(missing) == 0:
                    return
                traded = True
                

def calculate_next_purchase():
    print("calculate_next_purchase()")

    if distance_from_cards(cards_needed[PurchaseType.CITY], BOARD.resources) < 2 and \
       len(BOARD.own_settlements) > 0:
        return PurchaseType.CITY
    if len(BOARD.own_settlements) + len(BOARD.own_cities) < 3:
        if find_next_road(None, False) is None:
            return PurchaseType.SETTLEMENT
        else:
            return PurchaseType.ROAD
    return PurchaseType.DEV_CARD


def pick_cards_to_discard(amount):
    next_cards = cards_needed[calculate_next_purchase()]

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


def discard_cards(disc_cards):
    send({"action": 10, "data": disc_cards})


def create_trade(offered, wanted):
    data = {"offered": offered, "wanted": wanted}
    send({"action": 11, "data": data})


def send(data):
    data_in_json = json.dumps(data)
    QUEUE.put_nowait(data_in_json)


QUEUE = asyncio.Queue()
start_server = websockets.serve(handler, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
