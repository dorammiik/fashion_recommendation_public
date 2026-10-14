"""Create the local Preference schema. No API calls and no synthetic user data."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import argparse
from pathlib import Path

from fashion_recommendation_v2.storage import PreferenceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path('usage/preference.sqlite3'))
    parser.add_argument('--offline', action='store_true', help='Use a separate offline-eval database')
    args = parser.parse_args()
    with PreferenceStore(args.db, offline=args.offline) as store:
        tables = [r[0] for r in store.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    print(f'Preference DB ready: {args.db.resolve()}')
    print('Tables: ' + ', '.join(tables))


if __name__ == '__main__':
    main()
