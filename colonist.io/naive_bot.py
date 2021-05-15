import asyncio
import copy

from abstract_bot import Bot
from costs import COSTS
from dev_cards import DevCards
from purchase_types import PurchaseType
from resources import Resources

class NaiveBot(Bot):
    next_purchase = None
    event = None

    def __init__(self, board, own_color, queue):
        super().__init__(board, own_color, queue)

    # overriding abstract method
    def build_setup_settlement(self):
        print("Building settlement")
        settlement_index = self.find_setup_settlement_vertex()
        self.send_build_settlement(settlement_index)

    # overriding abstract method
    def build_setup_road(self):
        print("Building road")
        _, road_index = self.find_next_settlement(self.board.own_settlements[-1], True)

        if road_index is None:
            road_index = self.board.adjacency_map[self.board.own_settlements[-1]][0]["edge_index"]
        self.send_build_road(road_index)

    # overriding abstract method
    async def start_turn(self):
        self.send_throw_dice()

    # overriding abstract method
    async def play_turn(self):
        if self.board.own_dev_cards[DevCards.ROBBER] > 0:
            self.send_play_dev_card(DevCards.ROBBER)
            self.event = asyncio.Event()
            print("waiting for event")
            await self.event.wait()
            self.board.own_dev_cards[DevCards.ROBBER] -= 1

        print("Starting turn")
        self.next_purchase = self.calculate_next_purchase()
        print("next_purchase: {0}".format(self.next_purchase))

        if self.distance_from_cards(COSTS[self.next_purchase], self.board.resources) > 0:
            await self.trade_with_bank()
        if self.distance_from_cards(COSTS[self.next_purchase], self.board.resources) == 0:
            settlement_index, road_index = self.find_next_settlement()
            if self.next_purchase == PurchaseType.ROAD:
                self.send_build_road(road_index)
            if self.next_purchase == PurchaseType.SETTLEMENT:
                self.send_build_settlement(settlement_index)
            if self.next_purchase == PurchaseType.CITY:
                self.send_build_city(self.board.own_settlements[0])
            if self.next_purchase == PurchaseType.DEV_CARD:
                self.send_buy_dev_card()

        self.send_pass_turn()

    # overriding abstract method
    def move_robber(self):
        print("Moving robber")
        new_robber_tile_index = self.find_new_robber_tile()
        print("New robber tile index : {0}".format(new_robber_tile_index))
        self.send_move_robber(new_robber_tile_index)
    
    # overriding abstract method
    def rob(self, options):
        print("Robbing")
        self.send_rob(options[0])
        if self.event is not None:
            self.event.set()

    # overriding abstract method
    def discard_cards(self, amount):
        print("Discarding cards")
        cards = self.pick_cards_to_discard(amount)
        self.send_discard_cards(cards)

    # TODO: Rewrite to decouple from the colonist.io API
    # overriding abstract method
    def respond_to_trade(self, data):
        print("Responding to offer")
        # Respond to trade offer
        self.next_purchase = self.calculate_next_purchase()

        if self.is_favourable_trade(data):
            self.send_accept_trade(data.id)
        else:
            self.send_reject_trade(data.id)

    # overriding abstract method
    def handle_event(self, event_type):
        if self.event is not None:
            self.event.set()

    def find_next_settlement(self, settlement_index=None, is_setup=False):
        candidates = []

        if settlement_index is None:
            for index in self.board.own_settlements:
                candidates.extend(self.find_settlement_spots(index, [], 2))
        else:
            candidates.extend(self.find_settlement_spots(settlement_index, [], 2))

        if len(candidates) == 0:
            return None, None

        high_vertex_index = -1
        high_prod = -1
        high_path = []
        for entry in candidates:
            vertex_index = entry["vertex_index"]

            prod = self.board.find_vertex_production_by_index(vertex_index)
            if prod > high_prod and (not is_setup or prod <= 7):
                high_vertex_index = vertex_index
                high_prod = prod
                high_path = entry["path"]

        for edge_index in high_path:
            if self.board.edges[edge_index].owner == 0:
                return high_vertex_index, edge_index
        return high_vertex_index, None
    
    def evaluate_setup(self, production, harbor_types):
        score = 0
        total_production = sum(production.values())
        score += total_production

        for harbor_type in harbor_types:
            if harbor_type == 1:
                score *= 1.25
            else:
                score += production[Resources(harbor_type - 1)] / 1.5

        # Penalty if you have scare resources
        for resource, amount in production.items():
            if amount < 0.15 * total_production:
                penalty_multiplier = 1 - amount / (0.15 * total_production)
                score -= (0.2 * total_production) * penalty_multiplier

        return score

    def find_setup_settlement_vertex(self):
        i = high_index = -1
        high_score = -1
        for i, vertex in enumerate(self.board.vertices):
            if vertex.owner != 0 or vertex.restrictedStartingPlacement is True:
                continue
            
            prod = self.board.find_vertex_production_per_resource_by_index(i)
            for resource in Resources:
                prod[resource] += self.board.own_production[resource]

            harbor_types = set()
            harbor_types.update(self.board.own_harbors)
            if vertex.harborType != 0:
                harbor_types.add(vertex.harborType)

            score = self.evaluate_setup(prod, harbor_types)

            if score > high_score:
                high_score = score
                high_index = i

        return high_index

    def find_highest_producing_vertex(self):
        """ Loops over all vertices to find the highest producing spot
        where its still possible to build a settlement
        """

        i = high_index = -1
        high_prod = -1
        for i, vertex in enumerate(self.board.vertices):
            if vertex.owner != 0 or vertex.restrictedStartingPlacement is True:
                continue

            prod = self.board.find_vertex_production_by_index(i)
            if prod > high_prod:
                high_prod = prod
                high_index = i

        return high_index


    def find_settlement_spots(self, vertex_index, path, degree):
        if degree <= 0:
            vert = self.board.vertices[vertex_index]
            if vert.owner == 0 and not vert.restrictedStartingPlacement:
                return [{"vertex_index": vertex_index, "path": path}]
            else:
                return []

        candidates = []
        for entry in self.board.adjacency_map[vertex_index]:
            vertex = self.board.vertices[entry["vertex_index"]]
            edge = self.board.edges[entry["edge_index"]]
            if (not (len(path) > 0 and entry["edge_index"] == path[-1]) and # Don't travel backwards
            (vertex.owner == 0 or vertex.owner == self.own_color) and       # Make sure we can travel there
            (edge.owner == 0 or edge.owner == self.own_color)):             # Make sure we can travel there
                new_path = copy.deepcopy(path)
                new_path.append((entry["edge_index"]))
                candidates.extend(self.find_settlement_spots(entry["vertex_index"], new_path, degree - 1))

        return candidates

    def calc_missing_cards(self, needed, own_cards):
        dist = 0
        missing_cards = {}
        for resource, amount in needed.items():
            diff = max(0, amount - own_cards[resource])
            dist += diff
            if diff > 0:
                missing_cards[resource] = diff
        return dist, missing_cards

    def distance_from_cards(self, needed, own_cards):
        dist = 0
        for resource, amount in needed.items():
            dist += max(0, amount - own_cards[resource])

        return dist

    def is_favourable_trade(self, data):
        resources_after_trade = copy.deepcopy(self.board.resources)
        for card in data.offeredResources.cards:
            resources_after_trade[Resources(card)] += 1
        for card in data.wantedResources.cards:
            resources_after_trade[Resources(card)] -= 1
        needed = COSTS[self.calculate_next_purchase()]
        return self.distance_from_cards(needed, resources_after_trade) < self.distance_from_cards(needed, self.board.resources)


    def find_new_robber_tile(self):
        high_index = -1
        high_block = -1

        for i, tile in enumerate(self.board.tiles):
            if self.board.robber_tile == i:
                continue
            if tile.tileType == 0:
                continue  # desert tile doesn't have the _diceProbability attribute

            block = 0
            for vertex_index in self.board.tile_vertices[i]:
                vertex = self.board.vertices[vertex_index]

                if vertex.owner == self.own_color:
                    break
                if vertex.owner != 0:
                    block += tile._diceProbability * vertex.buildingType
            else:  # only runs if execution isnt broken during loop
                if block > high_block:
                    high_block = block
                    high_index = i

        return high_index

    async def trade_with_bank(self):
        print("trade_with_bank()")

        if self.distance_from_cards(COSTS[self.next_purchase], self.board.resources) == 0:
            return

        extra_resources = copy.deepcopy(self.board.resources)
        print(COSTS[self.next_purchase])
        for resource, amount in COSTS[self.next_purchase].items():
            extra_resources[resource] -= amount

        dist, missing = self.calc_missing_cards(COSTS[self.next_purchase], self.board.resources)

        print(list(missing)[0].value)
        
        traded = True
        while traded:
            traded = False
            for resource in Resources:
                offer_amount = self.board.bank_trades[resource]
                if extra_resources[resource] >= offer_amount:
                    print("Starting bank trade")

                    offered = [resource.value for x in range(offer_amount)]
                    wanted = [list(missing)[0].value]

                    self.send_create_trade(offered, wanted)
                    self.event = asyncio.Event()
                    print("waiting for event")
                    await self.event.wait()
                    print("done waiting for event")

                    extra_resources[resource] -= offer_amount
                    missing[list(missing)[0]] -= 1

                    if missing[list(missing)[0]] <= 0:
                        del missing[list(missing)[0]]
                    if len(missing) == 0:
                        return
                    traded = True
                    

    def calculate_next_purchase(self):
        return PurchaseType.DEV_CARD
        print("calculate_next_purchase()")
        if self.distance_from_cards(COSTS[PurchaseType.CITY], self.board.resources) < 1 and \
        len(self.board.own_settlements) > 0:
            print("city")
            return PurchaseType.CITY
        if len(self.board.own_settlements) + len(self.board.own_cities) < 4:
            print("settlement or road")
            if self.find_next_settlement()[1] is None:
                print("settlement")
                return PurchaseType.SETTLEMENT
            else:
                print("road")
                return PurchaseType.ROAD
        print("dev card")
        return PurchaseType.DEV_CARD


    def pick_cards_to_discard(self, amount):
        next_cards = COSTS[self.calculate_next_purchase()]

        non_discarded_cards = copy.deepcopy(self.board.resources)
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
