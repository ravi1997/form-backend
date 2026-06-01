from mongoengine import StringField, ListField
from models.base import BaseEmbeddedDocument


class TaxonomyItem(BaseEmbeddedDocument):
    """
    Taxonomy classification option configured by the form builder.
    """

    category_name = StringField(required=True, max_length=255)
    description = StringField(required=True, max_length=1000)
    keywords = ListField(StringField(), default=list)
