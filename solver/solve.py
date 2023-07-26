"""Solver interfaces/Classes used by app."""
import abc
import collections
import dataclasses
import logging
import typing as T

from detector import detect
from solver import converter
import solver.pythondds_min.adapter as dds_adapter


lgr = logging


# Abstract #

@dataclasses.dataclass
class Solution():
    hand: object
    hand_dict: T.List[T.Dict]
    dds_result: object


class IPresenter(abc.ABC):

    @abc.abstractmethod
    def present(self, solution: Solution):
        pass


class BridgeSolverBase(abc.ABC):
    cards: detect.CardDetection
    presenter: IPresenter

    solution_: Solution

    def __init__(self, cards, presenter) -> None:
        self.cards = cards
        self.presenter = presenter

    @abc.abstractmethod
    def transform(self):
        pass

    @abc.abstractmethod
    def assign(self):
        pass

    @abc.abstractmethod
    def list_unsure(self):
        pass

    @abc.abstractmethod
    def solve(self):
        pass

    def present(self):
        return self.presenter.present(self.solution_)


# Impl. #

class BridgeSolver(BridgeSolverBase):
    def __init__(self, cards, presenter) -> None:
        super().__init__(cards, presenter)
        self.converter = converter.get_deal_converter(reader=converter.Yolo5Reader())

    def transform(self):
        self.converter.read(self.cards)
        # self.converter.dedup(smart=True)  # yolo5 does not seem needing this
        missings, fps = self.converter.report_missing_and_fp()
        return missings, fps


    def assign(self):
        self.converter.assign()

    def list_unsure(self):
        pass  # TODO like 'bidly found %s only; would you like to fill in the remaining %s or redetect?'

    def solve(self):
        pbn_hand = self.converter.format_pbn()

        dds_result = dds_adapter.solve_hand(pbn_hand)
        lgr.debug("Got DDS result for pbn hand: %s", pbn_hand)

        self.solution_ = Solution(
            hand=pbn_hand,
            hand_dict=self.converter.list_assigned_cards(),
            dds_result=dds_result,
        )


class StringPresenter(IPresenter):
    def present(self, solution: Solution):
        formatted_hand = dds_adapter.format_hand(solution.hand)

        formatted_dd_result = dds_adapter.format_result(solution.dds_result)
        return formatted_hand, formatted_dd_result


class MonoStringPresenter(IPresenter):
    S, H, D, C = '\u2660', '\u2661', '\u2662', '\u2663'
    SYMBOL_MAP = {
        converter.SUIT_S: S,
        converter.SUIT_H: H,
        converter.SUIT_D: D,
        converter.SUIT_C: C,
    }
    HORI, VERT = '\u2500', '\u2502'
    TL, TR, BL, BR = '\u250c', '\u2510', '\u2514', '\u2518'

    MIN_WIDTH = 22  # 14 + 14 - square_width, for N having 13 cards in a suit
    SQUARE_WIDTH = 6

    def present(self, solution: Solution):
        formatted_hand = self._format_hand(solution.hand_dict)

        formatted_dd_result = dds_adapter.format_result(solution.dds_result)
        return formatted_hand, formatted_dd_result

    def _format_hand(self, hand) -> str:
        assert len(hand) == 52

        suit_map = collections.defaultdict(list)  # 'northd' -> list of cards
        for card in hand:
            player = card['hand']
            color, rank = card['name'][-1], card['name'][:-1]
            suit_map[player+color].append(rank)

        e_longest = self._longest_len(suit_map, converter.HAND_E) + 1  # for symbols
        w_longest = self._longest_len(suit_map, converter.HAND_W) + 1  # for symbols
        ew_min_width = max(e_longest, w_longest)
        ew_row_min_width = ew_min_width*2 + self.SQUARE_WIDTH + 2  # padding
        width = max(ew_row_min_width, self.MIN_WIDTH)

        ew_suit_width = (width-self.SQUARE_WIDTH-2) // 2
        ns_suit_width = self.SQUARE_WIDTH + 1 + ew_suit_width

        rows = []
        rows.append(self._align_l_r(self._format_suit(suit_map, 'north', 's'), ns_suit_width, width))
        rows.append(self._align_l_r(self._format_suit(suit_map, 'north', 'h'), ns_suit_width, width))
        rows.append(self._align_l_r(self._format_suit(suit_map, 'north', 'd'), ns_suit_width, width))
        rows.append(self._align_l_r(self._format_suit(suit_map, 'north', 'c'), ns_suit_width, width))

        t_bar = self.TL+self.HORI*4+self.TR
        h_bar = self.VERT+' '*4+self.VERT
        b_bar = self.BL+self.HORI*4+self.BR

        rows.append('')
        ws = self._align_l_r(self._format_suit(suit_map, 'west', 's'), w_longest, ew_suit_width)
        es = self._align_l_r(self._format_suit(suit_map, 'east', 's'), ew_suit_width, ew_suit_width)
        rows.append(' '.join([ws, t_bar, es]))

        wh = self._align_l_r(self._format_suit(suit_map, 'west', 'h'), w_longest, ew_suit_width)
        eh = self._align_l_r(self._format_suit(suit_map, 'east', 'h'), ew_suit_width, ew_suit_width)
        rows.append(' '.join([wh, h_bar, eh]))

        wd = self._align_l_r(self._format_suit(suit_map, 'west', 'd'), w_longest, ew_suit_width)
        ed = self._align_l_r(self._format_suit(suit_map, 'east', 'd'), ew_suit_width, ew_suit_width)
        rows.append(' '.join([wd, h_bar, ed]))

        wc = self._align_l_r(self._format_suit(suit_map, 'west', 'c'), w_longest, ew_suit_width)
        ec = self._align_l_r(self._format_suit(suit_map, 'east', 'c'), ew_suit_width, ew_suit_width)
        rows.append(' '.join([wc, b_bar, ec]))
        rows.append('')

        rows.append(self._align_l_r(self._format_suit(suit_map, 'south', 's'), ns_suit_width, width))
        rows.append(self._align_l_r(self._format_suit(suit_map, 'south', 'h'), ns_suit_width, width))
        rows.append(self._align_l_r(self._format_suit(suit_map, 'south', 'd'), ns_suit_width, width))
        rows.append(self._align_l_r(self._format_suit(suit_map, 'south', 'c'), ns_suit_width, width))

        return '\n'.join(rows)

    def _format_result(self, _) -> str:
        pass

    def _longest_len(self, suit_map, player):
        player_suits = (suit for pc, suit in suit_map.items() if pc.startswith(player))
        return max(len(s) for s in player_suits)

    def _format_suit(self, suit_map, player, color):
        cards = suit_map[player+color]
        sorted_cards = sorted(cards, key=converter.RANKS.index)
        mono_cards = ''.join('T' if c == '10' else c for c in sorted_cards) or '-'  # void
        formatted_suit = f'{self.SYMBOL_MAP[color]}{mono_cards}'
        return formatted_suit

    def _align_l_r(self, text, self_width, total_width):
        """Align left then right, to ensure center-aligned by adding trailing and leading spaces."""
        left_aligned = f'{{:<{self_width}}}'.format(text)
        left_right_aligned = f'{{:>{total_width}}}'.format(left_aligned)
        return left_right_aligned


class PrintPresenter(IPresenter):  # TODO ideally have another separate `View` and this only transforms
    def present(self, solution: Solution):
        formatted_hand = dds_adapter.format_hand(solution.hand)
        print(formatted_hand)

        formatted_dd_result = dds_adapter.format_result(solution.dds_result)
        print(formatted_dd_result)

        par_result = dds_adapter.calc_par(solution.dds_result)
        print(dds_adapter.format_par(par_result))
