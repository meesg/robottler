import json
from abc import ABC, abstractmethod

class Bot(ABC):
    board = None
    own_color = None
    _queue = None

    def __init__(self, board, own_color, queue):
        self.board = board
        self.own_color = own_color
        self._queue = queue

    @abstractmethod
    def build_setup_settlement(self):
        pass

    @abstractmethod
    def build_setup_road(self):
        pass

    @abstractmethod
    def use_turn(self):
        pass

    @abstractmethod
    def move_robber(self):
        pass

    @abstractmethod
    def rob(self, options):
        pass

    @abstractmethod
    def discard_cards(self):
        pass

    @abstractmethod
    def respond_to_trade(self):
        pass
    
    def send_build_road(self, road_index):
        self.send({"action": 0, "data": road_index})

    def send_build_settlement(self, settlement_index):
        self.send({"action": 1, "data": settlement_index})

    def send_build_city(self, settlement_index):
        self.send({"action": 2, "data": settlement_index})

    def send_buy_dev_card(self):
        self.send({"action": 3})

    def send_throw_dice(self):
        self.send({"action": 4})

    def send_pass_turn(self):
        self.send({"action": 5})

    def send_accept_trade(self, trade_id):
        self.send({"action": 6, "data": trade_id})

    def send_reject_trade(self, trade_id):
        self.send({"action": 7, "data": trade_id})

    def send_move_robber(self, tile_index):
        self.send({"action": 8, "data": tile_index})

    def send_rob(self, player):
        self.send({"action": 9, "data": player})

    def send_discard_cards(self, disc_cards):
        self.send({"action": 10, "data": disc_cards})

    def send_create_trade(self, offered, wanted):
        data = {"offered": offered, "wanted": wanted}
        self.send({"action": 11, "data": data})

    def send(self, data):
        data_in_json = json.dumps(data)
        self._queue.put_nowait(data_in_json)
