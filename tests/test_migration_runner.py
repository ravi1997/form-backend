from scripts.schema_migrations.runner import MigrationRunner


class _Collection:
    def __init__(self):
        self.rows = {}

    def create_index(self, *args, **kwargs):
        return None

    def find(self, query, projection):
        return [
            row for row in self.rows.values() if row.get("status") == query["status"]
        ]

    def update_one(self, query, update, upsert=False):
        version = query["version"]
        self.rows.setdefault(version, {"version": version})
        self.rows[version].update(update["$set"])


class _Db(dict):
    def __missing__(self, key):
        self[key] = _Collection()
        return self[key]


def test_migration_runner_handles_empty_package():
    runner = MigrationRunner(_Db(), package="missing.package")

    assert runner.migrate_up(dry_run=True) == []
    assert runner.migrate_down(dry_run=True) == []
