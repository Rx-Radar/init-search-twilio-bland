from firebase_admin import auth
from pharmacy_map import EXT_CVS
from twilio.rest import Client
from flask import jsonify
import time
import uuid
import requests

account_sid = 'AC3d433258fe9b280b01ba83afe272f438'
auth_token = '2cc106ae7b360c99a7be11cc4ea77c07'
client = Client(account_sid, auth_token)



# send sms message
def send_sms(twilio_client, phone_number, msg):
  TWILIO_PHONE_NUMBER = "+18337034125"
  try: 
    new_message = twilio_client.messages.create(to=phone_number, from_= TWILIO_PHONE_NUMBER, body=msg)
  except Exception as e: 
    return jsonify({"error": f"Internal error occured: send_sms {e}"})

def notify_user_all_bland_calls_failed(db, twilio_client, search_request_uuid):
    try: 
        # Get the 'troy_pharmacies' collection
        search_request_ref = db.collection('search_requests').document(search_request_uuid) 
        search_request_doc = search_request_ref.get().to_dict()

        user_phone_number = search_request_doc.get("user_id") # user phone number stored as user_id in search_request doc

        send_sms(twilio_client, user_phone_number, 'RxRadar update: Whoops, seems like we couldn\'t call any of the pharmacies for some reason. Maybe try again in a few minutes.')
    except Exception as e:
        return 

# places calls to all pharmacies
# returns:  success, error/msg, code
def call_all_pharmacies(db, twilio_client, search_request_uuid, prescription):
    try: 
        # Get the 'troy_pharmacies' collection
        pharmacies = db.collection('pharmacies').stream() # TODO change to troy pharmacies

        # call each pharmacy
        for pharmacy in pharmacies:

            try: 
                # Access document data
                pharm_data = pharmacy.to_dict()

                # Access specific fields
                pharm_uuid = pharm_data.get('pharmacy_uuid')
                pharm_phone = pharm_data.get('phone')
                pharm_name = pharm_data.get('name')

                # insert into calls db
                success, call_uuid, exc = db_add_call(db, search_request_uuid, pharm_uuid)
                if not success:
                    return False, None, jsonify({"error": "Internal error occured: failed to create call in calls db.", "exception": str(exc)})
            
                # initialize bland call
                success, out, exc = call_bland(search_request_uuid, call_uuid, pharm_phone, prescription)
                if not success:
                    try: 
                        # decrement num_calls parameter in search_request (so request is not waiting for more calls than will come through)
                        cur_num_calls = db.collection("search_requests").document(search_request_uuid).get().to_dict().get("num_calls")
                        search_request_update = {"num_calls": cur_num_calls - 1}
                        db.collection('search_requests').document(search_request_uuid).update(search_request_update)

                        # text user that all calls were failed to be placed with bland
                        if (cur_num_calls - 1) == 0:
                            notify_user_all_bland_calls_failed(db, twilio_client, search_request_uuid)
                            
                    except Exception as e:
                        return False, None, jsonify({"error": "Bland called failed Failed decrementing num_calls in search request", "exception": str(e)})
                    
                    # bland call could not be placed due to bland internal error --> decrease the number of calls placed by one + log 
                    print(f'{call_uuid} log: Bland call failed')
                
            except Exception as e:
                return False, None, jsonify({"error": "Internal error occured: failed to retrieve pharmacy details", "exception": str(e)})
    
    except Exception as e: 
        return False, None, jsonify({"error": "Internal error occured: failed to retrieve pharmacies from db", "exception": str(e)})

    # successs case
    return True, jsonify({"message": "pharmacy calls placed"}), None

# places a call to a pharmacy using bland
def call_bland(search_uuid, call_uuid, pharm_phone, prescription):
    parameters = {
        "call_uuid": call_uuid, # pass the uuid, this will become metadata on the actual request
        "request_uuid": search_uuid,
        "name": prescription["name"],
        "dosage": prescription["dosage"],
        "brand": prescription["brand_or_generic"],
        "quantity": prescription["quantity"],
        "type": prescription["type"]
    }
    
    # Convert parameters to URL query string
    query_string = "&amp;".join([f"{key}={value}" for key, value in parameters.items()])

    # TwiML
    twiml = f"""
    <Response>
        <Play digits="{EXT_CVS}"></Play>
        <Redirect>https://us-central1-rxradar.cloudfunctions.net/test-callback?{query_string}</Redirect>
    </Response>
    """

    """
    Note: in cloud function, extract url params like:
        name = request.args.get('name')
        dosage = request.args.get('dosage')
        brand = request.args.get('brand')
        quantity = request.args.get('quantity')
        medication_type = request.args.get('type')
    """

    response = client.calls.create(
        twiml=twiml,  # TwiML content as URL data
        to=pharm_phone,
        from_='+18337034125'
    )
    
    # call plased succesfully
    return True, jsonify({'message': 'call placed'}), None

# adds call to db
def db_add_call(db, search_request_uuid, pharm_uuid):
    print('even in this db_add_call')
    try:
        call_uuid = str(uuid.uuid4())
        # Current epoch time
        epoch_initiated = int(time.time())
        data = {
            "call_uuid": call_uuid,
            "search_request_uuid": search_request_uuid, 
            "pharmacy_uuid":pharm_uuid,
            "epoch_initiated": epoch_initiated,
            "epoch_finished": None,
            "status": "created",
            "result": None,
            "notes": None,
            "recording": None,
            "transcript": None
        }
        db.collection('calls').document(call_uuid).set(data)
        return  True, call_uuid, None

    except Exception as e:
        return False, None, str(e)

# creates a new search request
def db_add_search(req_obj, verfication_token, db, num_calls):
    try:
        # Generate a unique ID for the document
        unique_id = str(uuid.uuid4())

        # Current epoch time
        epoch_initiated = int(time.time())

        # prescription object
        user_location = req_obj["user_location"]
        phone_number = req_obj["phone_number"]
        med_name = req_obj["prescription"]["name"] 
        med_dosage = req_obj["prescription"]["dosage"]
        med_brand = req_obj["prescription"]["brand_or_generic"]
        med_quantity = req_obj["prescription"]["quantity"]
        med_type = req_obj["prescription"]["type"]

        # Data to be added
        data = {
            "search_request_uuid": unique_id,
            "user_id": phone_number,
            "user_location": user_location,
            "user_token": verfication_token,
            "prescription": {
                "name": med_name,
                "dosage": med_dosage,
                "brand": med_brand,
                "quantity": med_quantity,
                "type": med_type
            },
            "epoch_initiated": epoch_initiated,
            "calls": [],
            "num_calls": num_calls
        }

        # Add the data to a new document in the 'medications' collection
        db.collection("search_requests").document(unique_id).set(data)
        return True, unique_id, None
    
    # Catch any errors pushing to db
    except Exception:
        return False, None, Exception


# verifies user session token
def verify_user_token(token):
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        # The token is valid
        return uid
    except auth.InvalidIdTokenError:
        # The token is invalid
        return None


# validates user medication request body
def validate_request(request_data):
    required_fields = ['user_session_token', 'phone_number', 'user_location', 'prescription'] # required fields
    prescription_fields = ['name', 'dosage', 'brand_or_generic', 'quantity', 'type'] # required fields within medication

    # Check if all required fields exist
    for field in required_fields:
        if field not in request_data:
            return False, jsonify({'error': f'Missing required field: {field}'}), 400

    # Check if the types are correct
    if not isinstance(request_data.get('user_session_token'), str):
        return False, jsonify({'error': 'user_session_token must be a string'}), 400

    if not isinstance(request_data.get('phone_number'), str):
        return False, jsonify({'error': 'phone_number must be a string'}), 400

    if not isinstance(request_data.get('user_location'), str):
        return False, jsonify({'error': 'user_location must be a string'}), 400

    # Check prescription fields and types
    prescription = request_data.get('prescription')

    # check if prescription is empty 
    if not prescription:
        return False, jsonify({'error': 'prescription object can not be empty'}), 400

    # check that all the prescription fields exist
    for field in prescription_fields:
        if field not in prescription:
            return False, jsonify({'error': f'Missing required field inside prescription: {field}'}), 400

    # check that prescription object field types are valid
    if not isinstance(prescription.get('name'), str):
        return False, jsonify({'error': 'prescription name must be a string'}), 400
    if not isinstance(prescription.get('dosage'), str):
        return False, jsonify({'error': 'prescription dosage must be a string'}), 400
    if not isinstance(prescription.get('brand_or_generic'), str):
        return False, jsonify({'error': 'prescription brand_or_generic must be a string'}), 400
    if not isinstance(prescription.get('quantity'), str):
        return False, jsonify({'error': 'prescription quantity must be a string'}), 400
    if not isinstance(prescription.get('type'), str):
        return False, jsonify({'error': 'prescription type must be a string'}), 400

    # on valid
    return True, None, 200
