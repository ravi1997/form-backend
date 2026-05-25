import importlib
import inspect
import pkgutil
from datetime import datetime, timezone

from scripts.schema_migrations.base import BaseSchemaMigration


class MigrationRunner:
    def __init__(self, db, package="scripts.schema_migrations.versions"):
        self.db = db
        self.package = package
        self.state = db["schema_versions"]
        self.state.create_index("version", unique=True)

    def discover(self):
        try:
            package = importlib.import_module(self.package)
        except ModuleNotFoundError:
            return []

        migrations = []
        for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
            module = importlib.import_module(module_info.name)
            for _, cls in inspect.getmembers(module, inspect.isclass):
                if cls is BaseSchemaMigration:
                    continue
                if issubclass(cls, BaseSchemaMigration):
                    migrations.append(cls())
        return sorted(migrations, key=lambda migration: migration.version)

    def applied_versions(self):
        return {
            row["version"]
            for row in self.state.find({"status": "applied"}, {"version": 1})
        }

    def migrate_up(self, dry_run=False):
        applied = self.applied_versions()
        pending = [
            migration for migration in self.discover() if migration.version not in applied
        ]
        if dry_run:
            return [migration.version for migration in pending]

        for migration in pending:
            migration.up()
            self.state.update_one(
                {"version": migration.version},
                {
                    "$set": {
                        "version": migration.version,
                        "description": migration.description,
                        "status": "applied",
                        "applied_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
        return [migration.version for migration in pending]

    def migrate_down(self, target_version=None, dry_run=False):
        applied = self.applied_versions()
        migrations = [
            migration for migration in self.discover() if migration.version in applied
        ]
        migrations = sorted(migrations, key=lambda migration: migration.version, reverse=True)
        if target_version:
            migrations = [
                migration
                for migration in migrations
                if migration.version > target_version
            ]

        if dry_run:
            return [migration.version for migration in migrations]

        for migration in migrations:
            migration.down()
            self.state.update_one(
                {"version": migration.version},
                {
                    "$set": {
                        "status": "reverted",
                        "reverted_at": datetime.now(timezone.utc),
                    }
                },
            )
        return [migration.version for migration in migrations]
