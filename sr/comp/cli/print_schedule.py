# -*- coding: utf-8 -*-
import argparse


class ScheduleGenerator(object):
    def __init__(self, target, arenas, state):
        from reportlab.pdfgen import canvas

        self.canvas = canvas.Canvas(target)
        self.state = state
        self.width = 595
        self.height = 842
        self.margin = 40
        self.page_number = 0
        self.arenas = arenas
        self.columns = 2 + 4*len(arenas)

    def start_page(self, title='Match Schedule'):
        self.row_height = 800
        if self.page_number != 0:
            self.canvas.showPage()
        self.page_number += 1

        self.draw_header(title)
        self.draw_footer()
        self.draw_vertical_bars()
        self.draw_column_headings()

    def draw_header(self, text):
        self.canvas.setFont('Helvetica', 12)
        self.canvas.drawCentredString(self.width * 0.5, 820, text)

    def draw_footer(self):
        self.canvas.setFont("Helvetica", 8)
        self.canvas.drawCentredString(self.width*0.5, 10,
                "Page {} • Generated from state {}".format(self.page_number,
                                                           self.state[:7]))

    def draw_vertical_bars(self):
        for x in (140, 368):
            self.canvas.line(x, 30, x, 810)

    def draw_column_headings(self):
        headings = ['**Number**', '**Time**']
        for arena, config in self.arenas.items():
            headings += ['**{}**'.format(config.display_name), '', '', '']
        self.add_line(headings)

    def add_line(self, line):
        if len(line) != self.columns:
            raise ValueError("Incorrect column count")
        for i, cell in enumerate(line):
            if cell.startswith('**') and cell.endswith('**'):
                cell = cell[2:-2]
                self.canvas.setFont("Helvetica-Bold", 12)
            else:
                self.canvas.setFont("Helvetica", 10)
            self.canvas.drawCentredString(self.margin + i * (self.width - 2*self.margin) / (self.columns - 1),
                                          self.row_height, cell)
        self.canvas.line(self.margin*0.7, self.row_height - 3.5,
                         self.width-(self.margin*0.7), self.row_height - 3.5)
        self.row_height -= 14

    def generate(self, competition, highlight=()):
        def display(team):
            if team is None:
                return '–'
            if team in highlight:
                return '**' + team + '**'
            else:
                return team

        current_period = None

        for n, slot in enumerate(competition.schedule.matches):
            first_match = next(iter(slot.values()))
            period = competition.schedule.period_at(first_match.start_time)
            if period != current_period:
                current_period = period
                self.start_page(str(period))
                n = 0

            cells = ['', '']
            for arena in self.arenas:
                match = slot.get(arena)
                if match is not None:
                    cells += [display(team) for team in match.teams]
                    cells[0] = str(match.num)
                    cells[1] = str(match.start_time.strftime('%a %H:%M'))
                else:
                    cells += ['–', '–', '–', '–']
            if any(x.startswith('**') for x in cells):
                cells[0] = '**' + cells[0] + '**'
            self.add_line(cells)

            if n % 45 == 65:
                self.start_page(str(current_period))

    def write(self):
        self.canvas.save()


def command(settings):
    import os.path

    from sr.comp.comp import SRComp


    comp = SRComp(os.path.realpath(settings.compstate))

    generator = ScheduleGenerator(settings.output, arenas=comp.arenas,
                                  state=comp.state)

    highlight = settings.highlight if settings.highlight else ()
    generator.generate(comp, highlight=highlight)
    generator.write()


def add_subparser(subparsers):
    parser = subparsers.add_parser('print-schedule',
                                   help='print a shepherding sheet')
    parser.add_argument('compstate', help='competition state repository')
    parser.add_argument('-o', '--output', help='output file',
                        type=argparse.FileType('wb'), required=True)
    parser.add_argument('-H', '--highlight', nargs='+',
                        help="highlight specific team's matches")
    parser.set_defaults(func=command)
