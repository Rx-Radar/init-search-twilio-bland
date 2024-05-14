
import functions_framework
from cloudevents.http import CloudEvent
from flask import jsonify
from firebase_admin import credentials, firestore, initialize_app
from google.protobuf.json_format import MessageToDict
from google.protobuf.json_format import MessageToDict
from packages import util
from twilio.rest import Client
import functions_framework
from google.events.cloud import firestore as ge_firestore
import base64
import json
import yaml
import os

def load_yaml_file(filepath):
    with open(filepath, 'r') as file:
        data = yaml.safe_load(file)
    return data

# Use the function to load the configuration
config = load_yaml_file('config.yaml')

env = os.getenv("deployment_env")

TWILIO_ACCOUNT_SID = config[env]["twilio"]["account_sid"] 
TWILIO_AUTH_TOKEN = config[env]["twilio"]["auth_token"] 
FIREBASE_USERS_DB = config[env]["firebase"]["users_db"]

# Initialize Firebase Admin SDK with the service account key
cred = credentials.Certificate("firebase_creds.json")  # Update with your service account key file 
initialize_app(cred)
db = firestore.client() # set firestore client

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

"""
{
    "user_session_token": "12345abcde",
    "user_uuid": "dfsdfsd",
    "user_location": {
        lat: 0.00,
        lon: 0.00,
    },
    "prescription": {
        "name": "Focalin",
        "dosage": "10",
        "brand_or_generic": "Generic",
        "quantity": "30",
        "type": "Extended%20Release"
    }
}
"""
@functions_framework.cloud_event
def main(cloud_event: CloudEvent):
   # Create an instance of the Firestore DocumentEventData
    firestore_payload = ge_firestore.DocumentEventData()
    
    # Parse the CloudEvent data into the FirestoreDocumentEventData instance
    firestore_payload._pb.ParseFromString(cloud_event.data)
    
    # Convert the FirestoreDocumentEventData to a dictionary
    firestore_dict = MessageToDict(firestore_payload._pb)
    
    # Print the resulting dictionary
    print(firestore_dict)

    return "test"
    firestore_obj = firestore_payload.value.fields
    
    search_request_uuid = firestore_obj["search_request_uuid"].string_value
    
    prescription = firestore_obj["prescription"].struct_value.fields
    user_location = firestore_obj["user_location"].string_value.fields
    lat = user_location.fields["lat"].string_value
    lon = user_location.fields["lon"].string_value
    user_uuid = firestore_obj["user_uuid"]


    
    user_doc = db.collection(FIREBASE_USERS_DB).document(user_uuid).get()

    phone_number = user_doc.to_dict()["phone"]
    
    # calls pharmacies
    success, out, exc = util.call_all_pharmacies(db, twilio_client, search_request_uuid, prescription, lat, lon)
    if not success:
        return jsonify({'error': 'Calling pharmacies Failed', 'exception': str(exc)}), 500
    
    
    # update user doc with search information
    util.update_user_with_search(db=db, user_uuid=user_uuid, search_request_uuid=search_request_uuid)

    util.send_sms(twilio_client, "+12032248444", f"A new user has searched for a medication: {search_request_uuid}")
    util.send_sms(twilio_client, "+12037674296", f"A new user has searched for a medication: {search_request_uuid}")
    
    # return success message
    return jsonify({'message': 'Request is valid'}), 200





        