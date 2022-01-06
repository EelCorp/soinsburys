#!/usr/bin/env python3
import json
import pickle
import sys
import tty
import typing
import termios
from time import sleep
from dataclasses import dataclass
from escpos.printer import Usb
from enum import Enum
from functools import partial
from pathlib import Path

from rich.console import Console
from rich.table import Table

def getch():
  fd = sys.stdin.fileno()
  old_settings = termios.tcgetattr(fd)
  try:
    tty.setraw(sys.stdin.fileno())
    ch = sys.stdin.read(1)
  finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
  return ch

def input_single_char(prompt):
  sys.stdout.write(prompt)
  sys.stdout.flush()
  response = getch()
  sys.stdout.write("\n")
  return response

class Human(str, Enum):
    
    TIM = "t"
    DAN = "d"

class ItemTuple(typing.NamedTuple):

    uid: str
    name: str
    quantity: int
    total_cost: float

    def __str__(self):
        return f"{self.quantity} of {self.name} @ £{self.total_cost}"

@dataclass
class HumanState:

    name: str
    items: typing.List[ItemTuple]


def assign_items(person: Human, state, _, item: ItemTuple):
    print(f"Assigned {person.name} {item}")
    state[person].items.append(item)

def assign_with_cache(person: Human, state, cache, item: ItemTuple):
    print("Caching decision")
    assign_items(person, state, cache, item)
    cache[item.uid] = person
    with rick.open("wb") as fh:
        pickle.dump(cache, fh)

def ratio(state, _, item: ItemTuple):
    print(f"Splitting {item}, {item.quantity} units available")
    ratios = { person: float(input(f"Enter ratio for {person}: ") or "0") for person in Human }
    if sum(ratios.values()) != item.quantity:
        print("Learn to add you idiot")
        ratio(state, item)
    else:
        for person, dratio in ratios.items():
            state[person].items.append(ItemTuple(item.uid, item.name, dratio, item.total_cost * dratio / item.quantity))

def split(state, _, item: ItemTuple):
    print(f"Splitting {item} equally")
    for state in state.values():
        state.items.append(ItemTuple(item.uid, item.name, item.quantity / 2, item.total_cost / 2))

choices = {
    "d": partial(assign_items, Human.DAN),
    "t": partial(assign_items, Human.TIM),
    "D": partial(assign_with_cache, Human.DAN),
    "T": partial(assign_with_cache, Human.TIM),
    "s": split,
    "r": ratio,
    "i": lambda x,y,z: None,
}

state = {
    person: HumanState(name=str(person), items=[]) for person in Human
}

def perform_decision(state, cache, item: ItemTuple):
    try:
        chs = "/".join(choices)
        choice = input_single_char(f"Choose option: ({chs})")
        choices[choice](state, cache, item)
    except KeyError:
        perform_decision(state, item)

if __name__ == "__main__":
    print("Sainsburys YEET Application")

    if len(sys.argv) != 2:
        print("wtf mate, I need the name of the dodgy json file")
        sys.exit(1)

    path = Path(sys.argv[1])
    with path.open("r") as fh:
        data = json.loads(fh.read())
    
    rick = Path("cache.rick")
    if not rick.exists():
        with rick.open("wb") as fh:
            pickle.dump({"beans": "no"}, fh)
    with open(rick, "rb") as fh:
        cache = pickle.load(fh)

    print("Order number: " + data["order_uid"])

    expected_total = data["sub_total"]  # Cost of order without delivery fee

    assert data["total"] == data["sub_total"] + data["slot_price"]

    for item in data["order_items"]:
        quantity = item["quantity"]
        sub_total = item["sub_total"]
        name = item["product"]["name"]
        ea = sub_total / quantity
        uid = item["product"]["product_uid"]
        print(f"Ordered {quantity} of {name} for £{sub_total:.2f} ({ea:.2f} each)")

        item = ItemTuple(uid, name, quantity, sub_total)

        if uid in cache:
            assign_items(cache[uid], state, cache, item)
        else:
            perform_decision(state, cache, item)

    # Sanity check
    tt = sum(sum(i.total_cost for i in st.items) for st in state.values())
    if round(tt, 2) != expected_total:
        print("FUCK")
        print(f"Expected {expected_total} but cost {tt}")

    console = Console()

    for person, hs in state.items():
        table = Table(title=person.name)
        table.add_column("Item")
        table.add_column("Quantity")
        table.add_column("Cost")

        for item in hs.items:
            table.add_row(item.name, str(item.quantity), f"£{item.total_cost:.2f}")

        table.add_row("Delivery Cost", "0.5", "£" + str(data["slot_price"] / 2))
        sum_cost = sum(item.total_cost for item in hs.items) + (data["slot_price"] / 2)
        table.add_row("[bold]TOTAL", "", f"[bold]£{sum_cost:.2f}")
        console.print(table)

    pri = Usb(0x416,0x5011,profile="POS-5890", in_ep=0x81, out_ep=0x03)

    for person, hs in state.items():
        pri.image("eel.png", center=True)
        pri.ln()

        pri.set(font="a", align="center")
        pri.textln(person.name)
        pri.ln()
        pri.set(font="b", align="left")
        for item in hs.items:
            pri.textln(f"{item.quantity} {item.name} £{item.total_cost:.2f}")

        pri.set(font="a", align="center")
        sum_cost = sum(item.total_cost for item in hs.items) + (data["slot_price"] / 2)
        pri.ln()
        pri.textln(f"Total cost: £{sum_cost:.2f}")
        pri.print_and_feed(3)
        print("Cut")
        sleep(5)