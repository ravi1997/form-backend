from app import create_app
from models.User import User

app = create_app()
with app.app_context():
    User.objects(email='alice@hospital.org').delete()
    print("Deleted alice@hospital.org if she existed.")
