from models.theme import Theme
from schemas.theme import ThemeCreateSchema, ThemeSchema, ThemeUpdateSchema
from services.base import BaseService


class ThemeService(BaseService):
    def __init__(self):
        super().__init__(model=Theme, schema=ThemeSchema)

    def create_theme(self, schema: ThemeCreateSchema) -> ThemeSchema:
        return self.create(schema)

    def update_theme(
        self, theme_id: str, schema: ThemeUpdateSchema, organization_id: str
    ) -> ThemeSchema:
        return self.update(theme_id, schema, organization_id=organization_id)

    def soft_delete_theme(self, theme_id: str, organization_id: str) -> None:
        return self.delete(theme_id, organization_id=organization_id)
