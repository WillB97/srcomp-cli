from typing import Dict, List, NamedTuple, Optional

from sr.comp.scores import LeaguePosition
from sr.comp.types import ArenaName, GamePoints, MatchNumber, TLA

__description__ = "Show the game and league points achieved for each match"


class MatchCorner(NamedTuple):
    tla: TLA
    ranking: Optional[LeaguePosition]
    game: Optional[GamePoints]
    league: Optional[int]


class MatchResult(NamedTuple):
    num: MatchNumber
    arena: ArenaName
    display_name: str
    corners: Dict[int, MatchCorner]


def collect_match_info(comp, match):
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
            league_points[team] = None
            game_points[team] = None
            ranking[team] = None

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


def generate_displayed_headings(num_corners: int) -> List[str]:
    displayed_heading = ["Display Name", "Arena"]

    for idx in range(num_corners):
        displayed_heading.append(f"TLA {idx}")
        displayed_heading.append("Rank")
        displayed_heading.append("Game")
        displayed_heading.append("League")

    return displayed_heading


def generate_displayed_match(match: MatchResult) -> List[str]:
    displayed_match: List[str] = [match.display_name, match.arena]

    for tla, ranking, game, league in match.corners.values():
        displayed_match.append(tla)
        displayed_match.append("??" if ranking is None else str(ranking))
        displayed_match.append("???" if game is None else str(game))
        displayed_match.append("??" if league is None else str(league))

    return displayed_match


def command(settings):
    import os.path

    from tabulate import tabulate

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

    # TODO hide arena column w/ single arena?

    num_teams_per_arena = comp.num_teams_per_arena

    displayed_matches = [
        generate_displayed_match(match)
        for match in match_results
    ]

    print(tabulate(
        displayed_matches,
        headers=generate_displayed_headings(num_teams_per_arena),
        tablefmt='pretty',
        colalign=(
            ('center', 'center') + ('center', 'right', 'right', 'right') * num_teams_per_arena
        ),
    ))


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
