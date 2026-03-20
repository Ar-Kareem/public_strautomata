#! /usr/bin/env python
# coding: utf-8

import argparse
import sys
import time

from core import Core, DEFAULT_INITIAL_INSTRUCTION
from mars import MARS, EVENT_EXECUTED
from redcode import parse

DEFAULT_WINDOW = 18
DEFAULT_REFRESH = 100
DEFAULT_PROCESS_SAMPLE = 6

# Colors are dark and bright (kept for parity with graphics.py output ordering)
WARRIOR_COLORS = (((0, 0, 100), (0, 0, 255)),
                  ((0, 100, 0), (0, 255, 0)),
                  ((0, 100, 100), (0, 255, 255)),
                  ((100, 0, 0), (255, 0, 0)),
                  ((100, 0, 100), (255, 0, 255)),
                  ((100, 100, 0), (255, 255, 0)))


class CliMARS(MARS):
    """A MARS that tracks the last executed instruction for CLI rendering."""

    def __init__(self, *args, **kargs):
        super(CliMARS, self).__init__(*args, **kargs)
        self.last_executed = 0

    def core_event(self, warrior, address, event_type):
        if event_type == EVENT_EXECUTED:
            executed = address % len(self)
            self.last_executed = executed
            warrior.last_executed = executed


def clear_screen():
    print("\033[H\033[J", end="")


def render_state(simulation, round_num, cycle, total_cycles, active_warriors,
                 show_view=True, window=DEFAULT_WINDOW, clear=False, paused=False,
                 show_processes=True, process_sample=DEFAULT_PROCESS_SAMPLE):
    if clear:
        clear_screen()

    center = simulation.last_executed % len(simulation)
    status = "PAUSED" if paused else "RUNNING"
    print("Round %d | Cycle %d/%d | Active %d/%d | Focus %d | %s" % (
        round_num,
        cycle,
        total_cycles,
        len(active_warriors),
        len(simulation.warriors),
        center,
        status,
    ))

    if show_processes:
        total_processes = sum(len(warrior.task_queue) for warrior in simulation.warriors)
        print("Processes total: %d" % total_processes)
        for warrior in simulation.warriors:
            queue = warrior.task_queue
            last_exec = getattr(warrior, "last_executed", None)
            sample = [pc % len(simulation) for pc in queue[:process_sample]]
            extra = len(queue) - len(sample)
            tail = " +%d" % extra if extra > 0 else ""
            status_label = "active" if queue else "dead"
            last_label = "-" if last_exec is None else "#%s" % last_exec
            print("%s (%s): %s, %d [%s]%s | last %s" % (
                warrior.name,
                warrior.author,
                status_label,
                len(queue),
                ", ".join(str(pc) for pc in sample),
                tail,
                last_label,
            ))

    if not show_view:
        sys.stdout.flush()
        return

    start = center - window
    stop = center + window
    for address in range(start, stop + 1):
        trimmed = address % len(simulation)
        instruction = simulation[trimmed]
        marker = ">" if trimmed == center else " "
        print("%s %04d %s" % (marker, trimmed, instruction))

    sys.stdout.flush()


def prompt_command():
    while True:
        try:
            cmd = input("Paused: [Enter]=step, (c)ontinue, (n)ext, (q)uit, (?)help > ")
        except EOFError:
            return "quit"
        cmd = cmd.strip().lower()
        if cmd in ("", "s", "step"):
            return "step"
        if cmd in ("c", "p", "cont", "continue", "run"):
            return "continue"
        if cmd in ("n", "next"):
            return "next"
        if cmd in ("q", "quit", "exit"):
            return "quit"
        if cmd in ("?", "h", "help"):
            print("Commands: [Enter]/s=step, c=continue, n=next round, q=quit")
            continue
        print("Unknown command: %s" % cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MARS (Memory Array Redcode Simulator)')
    parser.add_argument('--rounds', '-r', metavar='ROUNDS', type=int, nargs='?',
                        default=1, help='Rounds to play')
    parser.add_argument('--paused', action='store_true', default=False,
                        help='Start each round paused')
    parser.add_argument('--size', '-s', metavar='CORESIZE', type=int, nargs='?',
                        default=8000, help='The core size')
    parser.add_argument('--cycles', '-c', metavar='CYCLES', type=int, nargs='?',
                        default=80000, help='Cycles until tie')
    parser.add_argument('--processes', '-p', metavar='MAXPROCESSES', type=int, nargs='?',
                        default=8000, help='Max processes')
    parser.add_argument('--length', '-l', metavar='MAXLENGTH', type=int, nargs='?',
                        default=100, help='Max warrior length')
    parser.add_argument('--distance', '-d', metavar='MINDISTANCE', type=int, nargs='?',
                        default=100, help='Minimum warrior distance')
    parser.add_argument('--refresh', '-f', metavar='REFRESH', type=int, nargs='?',
                        default=DEFAULT_REFRESH,
                        help='Cycles between screen refreshes (0 to disable)')
    parser.add_argument('--window', '-w', metavar='WINDOW', type=int, nargs='?',
                        default=DEFAULT_WINDOW,
                        help='Instructions to show above/below focus address')
    parser.add_argument('--delay', metavar='SECONDS', type=float, nargs='?',
                        default=0.0, help='Delay between cycles in seconds')
    parser.add_argument('--clear', action='store_true', default=False,
                        help='Clear the screen on each refresh')
    parser.add_argument('--no-view', action='store_true', default=False,
                        help='Disable instruction window display')
    parser.add_argument('--no-processes', action='store_true', default=False,
                        help='Disable process list display')
    parser.add_argument('--process-sample', metavar='COUNT', type=int, nargs='?',
                        default=DEFAULT_PROCESS_SAMPLE,
                        help='Process PCs to show per warrior')
    parser.add_argument('warriors', metavar='WARRIOR', type=argparse.FileType("r"), nargs='+',
                        help='Warrior redcode filename')

    args = parser.parse_args()

    if len(args.warriors) > len(WARRIOR_COLORS):
        print("Please specify a maximum of %d warriors." % len(WARRIOR_COLORS), file=sys.stderr)
        sys.exit(1)

    # build environment
    environment = {'CORESIZE': args.size,
                   'CYCLES': args.cycles,
                   'ROUNDS': args.rounds,
                   'MAXPROCESSES': args.processes,
                   'MAXLENGTH': args.length,
                   'MINDISTANCE': args.distance}

    # assemble warriors
    warriors = [parse(file, environment) for file in args.warriors]

    # initialize wins, losses, ties and color for each warrior
    for warrior, color in zip(warriors, WARRIOR_COLORS):
        warrior.wins = warrior.ties = warrior.losses = 0
        warrior.color = color

    # create MARS
    simulation = CliMARS(core=Core(size=args.size),
                         minimum_separation=args.distance,
                         max_processes=args.processes)
    simulation.warriors = warriors

    # control variables
    stop_rounds = False

    # for each round
    for round_num in range(1, args.rounds + 1):
        # reset simulation and load warriors
        simulation.reset(DEFAULT_INITIAL_INSTRUCTION)
        simulation.last_executed = 0
        for warrior in warriors:
            warrior.last_executed = None

        # start with all warriors active
        active_warriors = list(warriors)

        # how many warriors should be playing to skip to next round
        active_warrior_to_stop = 1 if len(warriors) >= 2 else 0

        # start paused if user requested from command line
        paused = bool(args.paused)
        next_round = False

        print()
        print("Starting round %d" % round_num)

        cycle = 0
        while cycle < args.cycles:
            if paused:
                render_state(
                    simulation,
                    round_num,
                    cycle,
                    args.cycles,
                    active_warriors,
                    show_view=not args.no_view,
                    window=args.window,
                    clear=args.clear,
                    paused=True,
                    show_processes=not args.no_processes,
                    process_sample=args.process_sample,
                )
                cmd = prompt_command()
                if cmd == "quit":
                    next_round = True
                    stop_rounds = True
                    break
                if cmd == "next":
                    next_round = True
                    break
                if cmd == "continue":
                    paused = False
                elif cmd == "step":
                    pass
                else:
                    continue

            # step one simulation in MARS
            simulation.step()
            cycle += 1

            if args.refresh > 0 and (cycle == 1 or cycle % args.refresh == 0) and not args.no_view:
                render_state(
                    simulation,
                    round_num,
                    cycle,
                    args.cycles,
                    active_warriors,
                    show_view=not args.no_view,
                    window=args.window,
                    clear=args.clear,
                    paused=False,
                    show_processes=not args.no_processes,
                    process_sample=args.process_sample,
                )

            if args.delay > 0:
                time.sleep(args.delay)

            to_remove = []
            for warrior in active_warriors:
                if not warrior.task_queue:
                    print("%s (%s) losses after %d cycles." % (warrior.name,
                                                               warrior.author,
                                                               cycle))
                    warrior.losses += 1
                    to_remove.append(warrior)

            for warrior in to_remove:
                active_warriors.remove(warrior)

            # if there's only one left, or are all dead, then stop simulation
            if len(active_warriors) <= active_warrior_to_stop:
                for warrior in active_warriors:
                    print("%s (%s) wins after %d cycles." % (warrior.name,
                                                             warrior.author,
                                                             cycle))
                    warrior.wins += 1
                break

        else:
            # running until max cycles: tie
            for warrior in active_warriors:
                if warrior.task_queue:
                    print("%s (%s) ties after %d cycles." % (warrior.name,
                                                             warrior.author,
                                                             cycle))
                    warrior.ties += 1

        if next_round:
            for warrior in active_warriors:
                if warrior.task_queue:
                    print("%s (%s) ties after %d cycles." % (warrior.name,
                                                             warrior.author,
                                                             cycle))
                    warrior.ties += 1

        if stop_rounds:
            break

    # print final results
    print()
    print("Final results: (%d rounds)" % round_num)
    print("%s %s %s %s" % ("Warrior (Author)".ljust(40), "wins".rjust(5),
                           "ties".rjust(5), "losses".rjust(5)))
    for warrior in warriors:
        print("%s %s %s %s" % (("%s (%s)" % (warrior.name, warrior.author)).ljust(40),
                               str(warrior.wins).rjust(5),
                               str(warrior.ties).rjust(5),
                               str(warrior.losses).rjust(5)))
