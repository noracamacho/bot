# db/firebase_config.py
import firebase_admin # type: ignore
from firebase_admin import credentials, firestore # type: ignore
from config import FIREBASE_CREDENTIALS_PATH

cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()


def update_user_roles(member):
    # Prepare the user data
    user_data = {
        'id': member.id,
        'name': member.name,
        'roles': [role.name for role in member.roles if role.name != "@everyone"]
    }

    # Get the reference to the user's document in Firestore
    user_ref = db.collection('users').document(str(member.id))
    
    # Set the user data
    user_ref.set(user_data, merge=True)