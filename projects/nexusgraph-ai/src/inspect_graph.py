from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_csv(name: str) -> list[dict[str, str]]:
    with (ROOT / 'graph' / name).open(newline='') as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    nodes = load_csv('nodes.csv')
    edges = load_csv('edges.csv')
    print(f'Nodes: {len(nodes)}')
    print(f'Edges: {len(edges)}')
    print('Node labels:')
    for label, count in sorted(Counter(row['label'] for row in nodes).items()):
        print(f'  {label}: {count}')
    print('Relationship types:')
    for rel, count in sorted(Counter(row['relationship'] for row in edges).items()):
        print(f'  {rel}: {count}')


if __name__ == '__main__':
    main()
