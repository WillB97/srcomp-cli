__description__ = "Show the game and league points achieved for each match"

from typing import Dict, List, Union, NamedTuple
from sr.comp.types import TLA, GamePoints, ArenaName, MatchNumber
from sr.comp.scores import LeaguePosition


class MatchCorner(NamedTuple):
    tla: TLA
    ranking: Union[LeaguePosition, str]  # to allow "???" to be used for unknown scores
    game: Union[GamePoints, str]
    league: Union[int, str]


class MatchResult(NamedTuple):
    num: MatchNumber
    arena: ArenaName
    display_name: str
    corners: Dict[int, MatchCorner]


def collect_match_info(comp, match) -> MatchResult:
    from sr.comp.match_period import MatchType
    from sr.comp.scores import degroup

    if match.type == MatchType.knockout:
        score_data = comp.scores.knockout
    elif match.type == MatchType.tiebreaker:
        score_data = comp.scores.tiebreaker
    elif match.type == MatchType.league:
        score_data = comp.scores.league

    match_id = (match.arena, match.num)

    if match_id in score_data.game_points:
        league_points = score_data.ranked_points[match_id]
        game_points = score_data.game_points[match_id]
        ranking = degroup(score_data.game_positions[match_id])
    else:
        league_points = {}
        game_points = {}
        ranking = {}
        for team in match.teams:
            league_points[team] = "???"
            game_points[team] = "???"
            ranking[team] = "???"

    corner_data: Dict[int, MatchCorner] = {}

    for corner, team in enumerate(match.teams):
        match_id = (match.arena, match.num)

        if team:  # corner occupied
            corner_data[corner] = MatchCorner(
                tla=team,
                ranking=ranking[team],
                game=game_points[team],
                league=league_points[team],
            )
        else:
            corner_data[corner] = MatchCorner(
                tla='',
                ranking='',
                game='',
                league='',
            )

    return MatchResult(
        num=match.num,
        arena=match.arena,
        display_name=match.display_name,
        corners=corner_data,
    )


def print_col(text):
        print(text, end='|')


def print_heading(num_corners, name_width, arena_name_width):
    print_col("".center(name_width + 1 + arena_name_width))
    for idx in range(num_corners):
        print_col(f"Zone {idx}".center(22))
    print()

    print_col("Display Name".center(name_width))
    print_col("Arena".center(arena_name_width))
    for idx in range(num_corners):
        print_col("TLA".center(5))
        print_col("Rank")
        print_col("Game")
        print_col("League")
    print()


def print_match(match: MatchResult, name_width, arena_name_width):
    print_col(match.display_name.center(name_width))
    print_col(match.arena.center(arena_name_width))

    for corner in match.corners.values():
        print_col(f" {corner.tla:<4}")
        print_col(f"{corner.ranking:>3} ")
        print_col(f"{corner.game:>3} ")
        print_col(f"{corner.league:>5} ")
    print()


def command(settings):
    import os.path

    from sr.comp.comp import SRComp

    comp = SRComp(os.path.realpath(settings.compstate))

    match_results: List[MatchResult] = []

    filter_tla = settings.tla
    skip_filter = filter_tla is None

    for slots in comp.schedule.matches:
        match_results.extend(
            collect_match_info(comp, match)
            for match in slots.values()
            if filter_tla in match.teams or skip_filter
        )

    if len(match_results) == 0:
        print("No matches found, TLA may be invalid")
        return

    # Calculate "Display Name" and "Arena" column widths
    display_name_width = 12  # start with width of label
    arena_name_width = 5  # start with width of label
    for match in match_results:
        display_name_width = max(display_name_width, len(match.display_name))
        arena_name_width = max(arena_name_width, len(match.arena))

    # Add some padding
    display_name_width += 2
    arena_name_width += 2

    # TODO hide arena column w/ single arena?

    num_teams_per_arena = comp.num_teams_per_arena

    print_heading(num_teams_per_arena, display_name_width, arena_name_width)

    for match in match_results:
        print_match(match, display_name_width, arena_name_width)


def add_subparser(subparsers):
    parser = subparsers.add_parser(
        'show-match-scores',
        help=__description__,
        description=__description__,
    )
    parser.add_argument(
        'compstate',
        help="competition state repo",
    )
    parser.add_argument(
        'tla',
        nargs='?',
        help="filter to matches containing this TLA",
    )
    parser.set_defaults(func=command)
