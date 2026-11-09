"""Find ProcTHOR houses whose objects support the long-horizon task families.

Reads the ProcTHOR-10K house JSON only; no simulator. Prints the houses that support the
most families, with their room count:

    python scripts/find_houses.py --split train --limit 2000 --top 20
"""

import argparse
from collections import Counter

# Each family needs every group; a group is satisfied by any one of its AI2-THOR types.
FAMILIES = {
    "breakfast_eggs": [["Egg"], ["Fridge"], ["Bowl", "Plate"], ["Microwave"], ["DiningTable"], ["Sink"]],
    "coffee": [["Mug", "Cup"], ["CoffeeMachine"], ["Sink"], ["Sofa", "ArmChair", "Desk"]],
    "toast": [["Bread"], ["Toaster"], ["Plate"], ["DiningTable"]],
    "salad": [["Lettuce"], ["Tomato"], ["Bowl"], ["DiningTable"], ["Fridge"]],
    "laundry": [["Cloth"], ["WashingMachine"], ["ClothesDryer"]],
    "clear_table": [["DiningTable"], ["Plate", "Bowl", "Mug", "Cup"], ["Sink"], ["ShelvingUnit", "Dresser"], ["Book"]],
}


def object_types(house):
    types = Counter()

    def walk(objects):
        for obj in objects:
            types[obj["id"].split("|")[0]] += 1
            walk(obj.get("children", []))

    walk(house["objects"])
    return types


def families_supported(types):
    return [
        name for name, groups in FAMILIES.items()
        if all(any(types[t] for t in group) for group in groups)
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="train", choices=["train", "val", "test"])
    parser.add_argument("--limit", type=int, default=2000, help="how many houses to scan")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-rooms", type=int, default=3)
    args = parser.parse_args()

    import prior

    houses = prior.load_dataset("procthor-10k")[args.split]
    found = []
    per_family = Counter()
    for index in range(min(args.limit, len(houses))):
        house = houses[index]
        families = families_supported(object_types(house))
        per_family.update(families)
        if len(house["rooms"]) >= args.min_rooms and families:
            found.append((len(families), index, len(house["rooms"]), families))

    print(f"houses supporting each family (of {min(args.limit, len(houses))}): {dict(per_family)}")
    for count, index, rooms, families in sorted(found, key=lambda f: (-f[0], f[1]))[: args.top]:
        print(f"  {args.split} {index:5d}  rooms={rooms}  {count} families: {', '.join(families)}")


if __name__ == "__main__":
    main()
