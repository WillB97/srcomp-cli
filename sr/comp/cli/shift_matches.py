"""
Shift the matches to start at the current time.

This is primarily aimed for development of SRComp related tooling, as a way to
reset the matches in a compstate to start at a convenient time.
"""


def command(args):
    from datetime import datetime, timedelta

    from .yaml_round_trip import dump as dump_yaml, load as load_yaml

    schedule = load_yaml(str(args.compstate / 'schedule.yaml'))

    old_start = schedule['match_periods'][args.focus][0]['start_time']
    new_start = datetime.now(old_start.tzinfo)
    # round to 1-2 minutes ahead
    new_start -= timedelta(
        seconds=new_start.second,
        microseconds=new_start.microsecond,
    )
    new_start += timedelta(minutes=2)

    dt = new_start - old_start

    for group in schedule['match_periods'].values():
        for entry in group:
            entry['start_time'] += dt
            entry['end_time'] += dt
            if 'max_end_time' in entry:
                entry['max_end_time'] += dt

    dump_yaml(str(args.compstate / 'schedule.yaml'), schedule)

    with (args.compstate / '.update-pls').open('w'):
        pass
    print(f"Shifted matches by {dt}")


def add_subparser(subparsers):
    from pathlib import Path

    parser = subparsers.add_parser(
        'shift-matches',
        help=__doc__.strip().splitlines()[0],
        description=__doc__,
    )
    parser.add_argument(
        'compstate',
        type=Path,
        help="competition state repository",
    )
    parser.add_argument(
        'focus',
        choices=('league', 'knockout'),
        help="match period to focus",
    )
    parser.set_defaults(func=command)
